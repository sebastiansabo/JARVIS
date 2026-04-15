#!/usr/bin/env python3
"""Commit digest — collects commits across JARVIS and jarvis-mobile over a
configurable period, asks Claude to translate + group them in Romanian, then
emails the digest via SMTP (defaults to the same Office365 account JARVIS uses
for invoice notifications).

Supports three periods via DIGEST_PERIOD env var:
    daily   (default) — last 24 hours, fires every day at 08:00 Romania
    weekly            — last 7 days,   fires Mondays at 08:00 Romania
    monthly           — last 30 days,  fires 1st of month at 08:00 Romania
                        (also includes a per-author timesheet table)

Environment variables (loaded from a .env file if present, with existing
os.environ values taking precedence):
    DIGEST_PERIOD          - "daily" | "weekly" | "monthly" (default: daily)
    ANTHROPIC_API_KEY      - Anthropic API key
    SMTP_HOST              - SMTP server hostname (default: smtp.office365.com)
    SMTP_PORT              - SMTP server port     (default: 587, STARTTLS)
    SMTP_USERNAME          - SMTP login username
    SMTP_PASSWORD          - SMTP login password
    SMTP_FROM_EMAIL        - From address (default: SMTP_USERNAME)
    SMTP_FROM_NAME         - From display name    (default: "JARVIS Digest")
    JARVIS_PATH            - Filesystem path to JARVIS checkout (default: .)
    MOBILE_PATH            - Filesystem path to jarvis-mobile checkout
    FORCE_RUN              - "1" to bypass the time-of-day / day-of-week guard

.env files are searched in this order (first match wins per key):
    1. $DOTENV_PATH (if set)
    2. ~/.jarvis-digest.env   (dedicated digest-only credentials)
    3. <repo root>/.env
    4. <repo root>/jarvis/.env (JARVIS backend fallback)

Runs the guard `should_run(period)` first so the script can be triggered twice
from cron (summer + winter DST) and still execute only at the right moment.
"""

from __future__ import annotations

import html
import os
import re
import smtplib
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from zoneinfo import ZoneInfo

import anthropic

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent


def load_dotenv(override: bool = False) -> None:
    """Minimal .env loader — no external dependency.

    Looks at a few well-known locations and sets any missing environment
    variables. Values already present in ``os.environ`` are kept (so GitHub
    Actions secrets always win over local .env files).
    """
    candidates: list[Path] = []
    if os.environ.get("DOTENV_PATH"):
        candidates.append(Path(os.environ["DOTENV_PATH"]))
    candidates.extend(
        [
            Path.home() / ".jarvis-digest.env",
            REPO_ROOT / ".env",
            REPO_ROOT / "jarvis" / ".env",
        ]
    )

    for path in candidates:
        if not path.is_file():
            continue
        try:
            for raw in path.read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                if line.startswith("export "):
                    line = line[len("export ") :]
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip()
                # Strip surrounding quotes
                if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
                    value = value[1:-1]
                if not key:
                    continue
                if override or key not in os.environ:
                    os.environ[key] = value
        except OSError:
            continue


load_dotenv()

ROMANIA_TZ = ZoneInfo("Europe/Bucharest")
_BASE_RECIPIENTS = "sebastian.sabo@gmail.com, sebastian.sabo@autoworld.ro"
_EXTENDED_RECIPIENTS = "sebastian.sabo@gmail.com, sebastian.sabo@autoworld.ro, boardaw@autoworld.ro"
MODEL = "claude-opus-4-6"

REPOS = [
    {"name": "JARVIS", "env": "JARVIS_PATH", "default": "."},
    {"name": "jarvis-mobile", "env": "MOBILE_PATH", "default": "../jarvis-mobile"},
]

PERIODS: dict[str, dict] = {
    "daily": {
        "title": "Digest Zilnic Commit-uri",
        "subject_prefix": "Digest zilnic commit-uri",
        "period_desc_ro": "ultimele 24 de ore",
        "prompt_window": "din ultimele 24 de ore",
        "git_since": "24 hours ago",
        "days_window": 1,
        "detail_level": "brief",
        "include_stats": False,
        "include_timesheet": False,
        "recipients": _BASE_RECIPIENTS,
    },
    "weekly": {
        "title": "Digest Săptămânal Commit-uri",
        "subject_prefix": "Digest săptămânal commit-uri",
        "period_desc_ro": "ultimele 7 zile",
        "prompt_window": "din ultimele 7 zile",
        "git_since": "7 days ago",
        "days_window": 7,
        "detail_level": "detailed",
        "include_stats": True,
        "include_timesheet": False,
        "recipients": _EXTENDED_RECIPIENTS,
    },
    "monthly": {
        "title": "Raport Lunar & Digest Commit-uri",
        "subject_prefix": "Raport lunar commit-uri",
        "period_desc_ro": "ultimele 30 de zile",
        "prompt_window": "din ultimele 30 de zile",
        "git_since": "30 days ago",
        "days_window": 30,
        "detail_level": "comprehensive",
        "include_stats": True,
        "include_timesheet": True,
        "recipients": _EXTENDED_RECIPIENTS,
    },
}

# Romanian localization for dates (used in headers and activity charts).
RO_MONTHS = {
    1: "Ianuarie", 2: "Februarie", 3: "Martie", 4: "Aprilie",
    5: "Mai", 6: "Iunie", 7: "Iulie", 8: "August",
    9: "Septembrie", 10: "Octombrie", 11: "Noiembrie", 12: "Decembrie",
}
RO_MONTHS_SHORT = {
    1: "Ian", 2: "Feb", 3: "Mar", 4: "Apr", 5: "Mai", 6: "Iun",
    7: "Iul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Noi", 12: "Dec",
}
RO_WEEKDAYS_SHORT = ["Lun", "Mar", "Mie", "Joi", "Vin", "Sâm", "Dum"]

# Module classification — maps file paths to business-meaningful areas.
# Patterns are tried in order; first match wins. Commits from jarvis-mobile
# are forced to "Aplicația mobilă" regardless of internal path.
MODULE_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("Resurse Umane & Pontaje",
     re.compile(r"(^|/)(hr|pontaj|timesheet|attendance|biostar|sincron|employee|salar)", re.I)),
    ("Vânzări & CRM",
     re.compile(r"(^|/)(crm|sales|lead|opportunity|customer|client)", re.I)),
    ("Facturare & Contabilitate",
     re.compile(r"(^|/)(invoice|facturare|anaf|efactura|accounting|billing|contab)", re.I)),
    ("Marketing & Campanii",
     re.compile(r"(^|/)(marketing|campaign|newsletter|promo)", re.I)),
    ("Documente & Arhivă",
     re.compile(r"(^|/)(document|archive|upload|storage)", re.I)),
    ("Parc Auto & Flotă",
     re.compile(r"(^|/)(fleet|vehicle|car|parc_auto|service_auto)", re.I)),
    ("Autentificare & Securitate",
     re.compile(r"(^|/)(auth|login|security|permission|rbac|jwt|session)", re.I)),
    ("Notificări & Mesagerie",
     re.compile(r"(^|/)(notif|mail|email|sms|push|digest|alert)", re.I)),
    ("Bază de date & Migrații",
     re.compile(r"(^|/)(migration|alembic|schema\.sql|seed|fixtures?)", re.I)),
    ("Infrastructură & DevOps",
     re.compile(r"(^|/)(\.github|docker|k8s|deploy|workflow|terraform|ansible|ci|cd)", re.I)),
    ("Scripturi & Automatizări",
     re.compile(r"(^|/)(scripts?|tools?|automation|cron)", re.I)),
    ("Frontend & UI",
     re.compile(r"(^|/)(frontend|ui|components?|pages?|views?|templates?|static|assets?|styles?)", re.I)),
    ("Backend & API",
     re.compile(r"(^|/)(api|backend|server|routes?|endpoints?|services?)", re.I)),
    ("Rapoarte & Analitică",
     re.compile(r"(^|/)(report|analytics|dashboard|stats?|metrics?)", re.I)),
    ("Testare & Calitate",
     re.compile(r"(^|/)(tests?|spec|e2e|pytest|jest)", re.I)),
]


def format_ro_date(dt: datetime, short_month: bool = False) -> str:
    """Format a datetime as 'DD Month YYYY' in Romanian."""
    month_name = (RO_MONTHS_SHORT if short_month else RO_MONTHS)[dt.month]
    return f"{dt.day} {month_name} {dt.year}"


def classify_module(file_path: str, repo_name: str) -> str:
    """Map a repo-relative file path to a business-meaningful module label."""
    if repo_name == "jarvis-mobile":
        return "Aplicația mobilă"
    for label, pattern in MODULE_PATTERNS:
        if pattern.search(file_path):
            return label
    parts = file_path.split("/", 1)
    if parts and parts[0]:
        return f"Alte zone ({parts[0]}/)"
    return "Alte zone"


def get_period() -> tuple[str, dict]:
    key = os.environ.get("DIGEST_PERIOD", "daily").lower().strip()
    if key not in PERIODS:
        print(f"Unknown DIGEST_PERIOD={key!r}, falling back to 'daily'", file=sys.stderr)
        key = "daily"
    return key, PERIODS[key]


def should_run(period: str) -> bool:
    """Return True if the script should execute right now for this period.

    All periods fire at 08:xx Europe/Bucharest.
      - daily  : every day
      - weekly : Mondays only (weekday()==0)
      - monthly: 1st of the month only
    """
    now = datetime.now(ROMANIA_TZ)
    if now.hour != 8:
        return False
    if period == "daily":
        return True
    if period == "weekly":
        return now.weekday() == 0
    if period == "monthly":
        return now.day == 1
    return False


def estimate_hours_worked(commits: list[dict]) -> float:
    """Estimate hours worked from a flat list of commits (all repos combined).

    Uses the standard git-hours heuristic:
      - Group commits by author.
      - For each author, sort commits by timestamp.
      - If two consecutive commits are within MAX_COMMIT_DIFF_MINUTES of each
        other, count the gap between them as working time.
      - Otherwise treat the next commit as a new session and add
        FIRST_COMMIT_ADDITION_MINUTES to cover pre-commit work (the first
        commit of every session also gets this addition).
    """
    MAX_COMMIT_DIFF_MINUTES = 120
    FIRST_COMMIT_ADDITION_MINUTES = 120

    by_author: dict[str, list[datetime]] = {}
    for c in commits:
        try:
            ts = datetime.fromisoformat(c["date"])
        except (KeyError, ValueError):
            continue
        by_author.setdefault(c.get("email") or c.get("author", "unknown"), []).append(ts)

    total_minutes = 0.0
    for author_commits in by_author.values():
        author_commits.sort()
        if not author_commits:
            continue
        minutes = FIRST_COMMIT_ADDITION_MINUTES  # first commit of first session
        for prev, curr in zip(author_commits, author_commits[1:]):
            gap_minutes = (curr - prev).total_seconds() / 60.0
            if gap_minutes < MAX_COMMIT_DIFF_MINUTES:
                minutes += gap_minutes
            else:
                # New session — add the pre-work buffer
                minutes += FIRST_COMMIT_ADDITION_MINUTES
        total_minutes += minutes

    return round(total_minutes / 60.0, 1)


def collect_commits(repo_path: str, git_since: str) -> list[dict]:
    """Collect commits from all branches since `git_since` (a git log --since arg).

    Uses ASCII Unit Separator (0x1f) between fields and Record Separator (0x1e)
    between commits so commit messages can contain any character safely.
    """
    fmt = "%H%x1f%an%x1f%ae%x1f%aI%x1f%s%x1f%b%x1e"
    result = subprocess.run(
        [
            "git",
            "-C",
            repo_path,
            "log",
            "--all",
            "--no-merges",
            f"--since={git_since}",
            f"--pretty=format:{fmt}",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    commits: list[dict] = []
    for raw in result.stdout.split("\x1e"):
        raw = raw.strip()
        if not raw:
            continue
        parts = raw.split("\x1f")
        if len(parts) < 5:
            continue
        commits.append(
            {
                "sha": parts[0][:8],
                "author": parts[1],
                "email": parts[2],
                "date": parts[3],
                "subject": parts[4],
                "body": parts[5] if len(parts) > 5 else "",
            }
        )
    return commits


def collect_commit_stats(repo_path: str, git_since: str) -> dict[str, dict]:
    """Per-commit numstat (file list + lines added/removed).

    Returns a dict keyed by 8-char SHA prefix::

        {
            "a1b2c3d4": {
                "files": ["path/to/file.py", ...],
                "lines_added": 42,
                "lines_removed": 8,
            },
            ...
        }
    """
    result = subprocess.run(
        [
            "git",
            "-C",
            repo_path,
            "log",
            "--all",
            "--no-merges",
            f"--since={git_since}",
            "--pretty=format:__COMMIT__%H",
            "--numstat",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    stats: dict[str, dict] = {}
    current_sha: str | None = None
    for line in result.stdout.splitlines():
        if line.startswith("__COMMIT__"):
            current_sha = line[len("__COMMIT__") :][:8]
            stats[current_sha] = {"files": [], "lines_added": 0, "lines_removed": 0}
            continue
        if not line.strip() or current_sha is None:
            continue
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        added_s, removed_s, path = parts
        # Binary files show up as "-\t-\t..."
        added = int(added_s) if added_s.isdigit() else 0
        removed = int(removed_s) if removed_s.isdigit() else 0
        # Handle renames: "old => new" or "path/{old => new}/rest"
        if " => " in path:
            m = re.match(r"(.*)\{(.*) => (.*)\}(.*)", path)
            if m:
                path = f"{m.group(1)}{m.group(3)}{m.group(4)}"
            else:
                path = path.split(" => ", 1)[1]
        stats[current_sha]["files"].append(path)
        stats[current_sha]["lines_added"] += added
        stats[current_sha]["lines_removed"] += removed
    return stats


def build_stats_section(
    commits_by_repo: dict[str, list[dict]],
    stats_by_repo: dict[str, dict[str, dict]],
    period_config: dict,
) -> str:
    """Build the statistics + activity + module-breakdown section.

    Only rendered for weekly/monthly. Produces:
      - Key headline metrics
      - Daily activity bar chart (Romanian weekday/month labels)
      - Module distribution table (commits + lines changed, sorted by lines)
      - Top contributors table (author / commits / estimated hours)
    """
    all_commits: list[tuple[str, dict]] = [
        (repo, c) for repo, cs in commits_by_repo.items() for c in cs
    ]
    if not all_commits:
        return ""

    total_commits = len(all_commits)
    total_hours = estimate_hours_worked([c for _, c in all_commits])
    authors: set[str] = {c["author"] for _, c in all_commits if c.get("author")}

    # Aggregate line-level stats per module (using numstat).
    total_added = 0
    total_removed = 0
    unique_files: set[str] = set()
    module_commits: dict[str, set[str]] = defaultdict(set)
    module_lines: dict[str, int] = defaultdict(int)

    for repo_name, commits in commits_by_repo.items():
        repo_stats = stats_by_repo.get(repo_name, {})
        for c in commits:
            s = repo_stats.get(c["sha"])
            if not s:
                continue
            total_added += s["lines_added"]
            total_removed += s["lines_removed"]
            commit_modules: set[str] = set()
            for fp in s["files"]:
                unique_files.add(f"{repo_name}:{fp}")
                module = classify_module(fp, repo_name)
                commit_modules.add(module)
                # Rough per-file line weight: added+removed on the file's line.
                # numstat only gives us per-file counts, not per-module, so
                # we distribute them naively one file at a time.
            # Count each commit once per module it touches.
            for module in commit_modules:
                module_commits[module].add(c["sha"])
            # Distribute total commit lines evenly across touched modules so
            # large multi-module commits don't skew a single module.
            commit_lines = s["lines_added"] + s["lines_removed"]
            if commit_modules and commit_lines:
                share = commit_lines / len(commit_modules)
                for module in commit_modules:
                    module_lines[module] += share

    # Per-day distribution for the activity chart.
    by_day: dict[datetime, int] = defaultdict(int)
    for _, c in all_commits:
        try:
            dt = datetime.fromisoformat(c["date"])
        except (KeyError, ValueError):
            continue
        day = dt.astimezone(ROMANIA_TZ).date()
        by_day[day] += 1  # type: ignore[index]
    active_days = len(by_day)

    # Busiest day
    busiest_day_str = "—"
    if by_day:
        busiest_day, busiest_count = max(by_day.items(), key=lambda kv: kv[1])
        busiest_day_dt = datetime.combine(busiest_day, datetime.min.time())
        busiest_day_str = (
            f"{RO_WEEKDAYS_SHORT[busiest_day_dt.weekday()]} "
            f"{format_ro_date(busiest_day_dt, short_month=True)} "
            f"({busiest_count} commit-uri)"
        )

    lines: list[str] = []
    lines.append("## Statistici cheie")
    lines.append("")
    lines.append(
        f"- **{total_commits} commit-uri** livrate de **{len(authors)} dezvoltatori**"
        f" în **{active_days} zile active**"
    )
    lines.append(f"- **~{total_hours}h lucrate** (estimare pe baza istoricului Git)")
    lines.append(
        f"- **+{total_added:,} linii adăugate** · **−{total_removed:,} linii șterse**"
        f" · **{len(unique_files):,} fișiere atinse**"
    )
    lines.append(f"- **Cea mai activă zi:** {busiest_day_str}")
    lines.append("")

    # Activity chart — one row per day across the whole window.
    if by_day:
        lines.append("## Activitate zilnică")
        lines.append("")
        lines.append("```")
        window_days = period_config.get("days_window", 7)
        today = datetime.now(ROMANIA_TZ).date()
        start = today - timedelta(days=window_days - 1)
        max_count = max(by_day.values()) or 1
        max_bar = 28
        day = start
        while day <= today:
            count = by_day.get(day, 0)
            bar_len = int(round((count / max_count) * max_bar)) if count else 0
            bar = "█" * bar_len
            weekday_label = RO_WEEKDAYS_SHORT[day.weekday()]
            day_label = (
                f"{weekday_label} {day.day:2d} {RO_MONTHS_SHORT[day.month]}"
            )
            lines.append(f"{day_label}  {bar} {count if count else ''}".rstrip())
            day += timedelta(days=1)
        lines.append("```")
        lines.append("")

    # Module distribution table (sorted by approximate line weight).
    if module_commits:
        lines.append("## Distribuție pe module")
        lines.append("")
        lines.append("| Modul | Commit-uri | Linii modificate | % din activitate |")
        lines.append("|---|---:|---:|---:|")
        total_line_weight = sum(module_lines.values()) or 1
        rows = sorted(
            module_commits.keys(),
            key=lambda m: (-module_lines.get(m, 0), -len(module_commits[m]), m),
        )
        for module in rows:
            commits_count = len(module_commits[module])
            lines_weight = int(round(module_lines.get(module, 0)))
            pct = module_lines.get(module, 0) / total_line_weight * 100
            lines.append(
                f"| {module} | {commits_count} | {lines_weight:,} | {pct:.0f}% |"
            )
        lines.append("")

    # Top contributors — same data as timesheet but available for weekly too.
    by_author: dict[str, list[dict]] = defaultdict(list)
    for _, c in all_commits:
        by_author[c.get("author") or "necunoscut"].append(c)

    lines.append("## Top contribuitori")
    lines.append("")
    lines.append("| Dezvoltator | Commit-uri | Zile active | Ore estimate |")
    lines.append("|---|---:|---:|---:|")
    author_rows: list[tuple[str, int, int, float]] = []
    for name, author_commits in by_author.items():
        hours = estimate_hours_worked(author_commits)
        days_set: set = set()
        for c in author_commits:
            try:
                days_set.add(datetime.fromisoformat(c["date"]).date())
            except (KeyError, ValueError):
                continue
        author_rows.append((name, len(author_commits), len(days_set), hours))
    for name, n, d, h in sorted(author_rows, key=lambda r: (-r[3], -r[1], r[0])):
        lines.append(f"| {name} | {n} | {d} | ~{h}h |")
    lines.append("")

    return "\n".join(lines)


BUSINESS_CATEGORIES_RO = [
    "**Resurse Umane & Pontaje**",
    "**Vânzări & Clienți (CRM)**",
    "**Contabilitate & Facturare**",
    "**Marketing & Comunicare**",
    "**Documente & Arhivă**",
    "**Parc Auto & Flotă**",
    "**Aplicația mobilă**",
    "**Rapoarte & Analitică**",
    "**Notificări & Alerte**",
    "**Autentificare & Securitate**",
    "**Infrastructură & Operațiuni** (viteză, stabilitate, deploy-uri)",
]


def _build_prompt_brief(window: str) -> list[str]:
    """Instructions for daily digest — one bullet per commit, concise."""
    cats = "\n".join(f"   - {c}" for c in BUSINESS_CATEGORIES_RO)
    return [
        f"Ai primit lista de commit-uri Git {window} pentru platforma JARVIS (aplicația internă Autoworld: web + mobil).",
        "",
        "PUBLIC ȚINTĂ: directorul general și echipa de management (C-level). NU sunt programatori.",
        "Ei vor să înțeleagă IMPACTUL DE BUSINESS al muncii echipei, nu detaliile tehnice.",
        "",
        "Sarcina ta:",
        "1. **Traduce fiecare modificare în limbaj de business**, nu tehnic. Transformă jargonul dezvoltatorilor în beneficii vizibile:",
        "   - NU folosi cuvinte precum: commit, endpoint, API, refactor, bug fix, deploy, repo, SHA, PR, merge, backend, frontend, schema, query, cache, hotfix, migration.",
        "   - DA folosește formulări de tipul: „Am adăugat posibilitatea...\", „Am îmbunătățit viteza...\", „Am corectat o eroare care afecta...\", „Am activat o funcție nouă pentru...\", „Am făcut ca X să funcționeze mai fiabil\".",
        "2. **Concentrează-te pe VALOARE, nu pe munca tehnică.** Răspunde la întrebarea: „Ce poate face un utilizator acum ce nu putea face ieri?\" sau „Ce problemă a dispărut pentru echipă / clienți?\".",
        "3. **FIECARE COMMIT = UN BULLET SEPARAT.** Nu uni mai multe commit-uri într-un singur bullet.",
        "4. **Grupează bullet-urile pe arii funcționale ale afacerii** (ordinea categoriilor reflectă prioritatea). Afișează doar categoriile care au commit-uri:",
        cats,
        "5. **Începe cu un sumar executiv de 2–3 propoziții** care rezumă ziua în ansamblu și subliniază impactul major.",
        "6. **Fiecare bullet = 1 propoziție scurtă**, începând cu un verb la timpul trecut („Am adăugat\", „Am îmbunătățit\", „Am corectat\", „Am automatizat\").",
        "7. **Acoperă TOATE commit-urile primite** — numărul de bullet-uri = numărul de commit-uri primite.",
        "8. **La finalul fiecărui bullet** adaugă SHA-ul scurt al commit-ului în italics, între paranteze. Exemplu: „Am adăugat exportul pontajelor în Excel. _(a1b2c3d4)_\".",
        "9. Vorbește la persoana întâi plural („echipa\" / „noi\").",
        "10. Fără concluzie, fără „Cu stimă\", fără CTA. Doar conținutul util. Folosește Markdown curat.",
        "",
        "**Lungime: email echilibrat.** Un bullet pentru fiecare commit, formulat clar și orientat pe business.",
    ]


def _build_prompt_detailed(window: str) -> list[str]:
    """Instructions for weekly digest — per-area narrative + selective bullets."""
    cats = "\n".join(f"   - {c}" for c in BUSINESS_CATEGORIES_RO)
    return [
        f"Ai primit lista de commit-uri Git {window} pentru platforma JARVIS (aplicația internă Autoworld: web + mobil).",
        "",
        "PUBLIC ȚINTĂ: directorul general și echipa de management (C-level). NU sunt programatori.",
        "Aceasta este SINTEZA SĂPTĂMÂNALĂ — managementul vrea să înțeleagă ce s-a obținut în ansamblu, pe arii ale afacerii, nu să citească o listă brută de 100+ schimbări.",
        "",
        "STRUCTURĂ OBLIGATORIE A OUTPUT-ULUI:",
        "",
        "## Sumar executiv",
        "**4–6 propoziții** care rezumă săptămâna: direcția majoră de efort, 2–3 realizări cu impact vizibil, zone care au avansat cel mai mult și, dacă există, un indicator de risc sau blocaj vizibil în commit-uri (ex. multe corecturi într-o zonă = zonă fragilă).",
        "",
        "## Progres pe arii funcționale",
        "Pentru fiecare arie de business care a avut activitate, emite o sub-secțiune cu:",
        "1. Un titlu `### **Nume arie**` (folosește categoriile de mai jos, în ordine de prioritate).",
        "2. **1–2 propoziții de context** care descriu tema săptămânii în acea arie (ex. „Am continuat consolidarea pontajelor automate, cu accent pe reconciliere și export.\").",
        "3. **3–8 bullet-uri** care grupează commit-urile similare în realizări concrete de business. Poți uni 2–5 commit-uri apropiate ca temă într-un singur bullet dacă rezultă o formulare mai clară. Fiecare bullet = 1 propoziție, verb la timpul trecut, orientat pe impact.",
        "4. La finalul fiecărui bullet, în italics și între paranteze, enumeră SHA-urile scurte ale commit-urilor care stau la baza lui, separate prin virgulă. Exemplu: „Am accelerat exportul Excel al pontajelor. _(a1b2c3d4, e5f6g7h8)_\".",
        "",
        "Categoriile disponibile (folosește DOAR acelea care au activitate):",
        cats,
        "",
        "REGULI DE FORMULARE:",
        "- Zero jargon tehnic. NU folosi: commit, endpoint, API, refactor, deploy, repo, PR, merge, schema, query, cache, migration, bug fix, hotfix.",
        "- Fiecare bullet începe cu un verb la timpul trecut („Am adăugat\", „Am îmbunătățit\", „Am corectat\", „Am automatizat\", „Am extins\").",
        "- Vorbește la persoana întâi plural („echipa\" / „noi\").",
        "- NU include nume de fișiere, funcții sau dezvoltatori în bullet-uri.",
        "- NU uni arii diferite. Fiecare arie rămâne izolată sub propriul titlu.",
        "- Acoperă TOATE commit-urile primite: fiecare SHA trebuie să apară măcar o dată într-un bullet. Dacă un commit e banal (ex. mic refactor), îl poți menționa la „Infrastructură & Operațiuni\".",
        "- Nu adăuga concluzie, „Cu stimă\" sau CTA. Nu include alte titluri în afara celor cerute.",
        "",
        "**Lungime: raport săptămânal dens dar lizibil.** Între 400 și 700 de cuvinte.",
    ]


def _build_prompt_comprehensive(window: str) -> list[str]:
    """Instructions for monthly report — strategic + thematic + per-area narrative."""
    cats = "\n".join(f"   - {c}" for c in BUSINESS_CATEGORIES_RO)
    return [
        f"Ai primit lista de commit-uri Git {window} pentru platforma JARVIS (aplicația internă Autoworld: web + mobil).",
        "",
        "PUBLIC ȚINTĂ: directorul general și echipa de management (C-level). NU sunt programatori.",
        "Aceasta este SINTEZA LUNARĂ — un raport strategic pe care managementul îl folosește pentru a înțelege cum a evoluat platforma, ce s-a livrat, unde s-au concentrat resursele și care sunt semnalele pentru luna următoare.",
        "",
        "STRUCTURĂ OBLIGATORIE A OUTPUT-ULUI:",
        "",
        "## Sumar executiv",
        "**6–10 propoziții** bine construite care răspund la întrebările:",
        "1. Care a fost direcția strategică a lunii (ce am consolidat, ce am lansat)?",
        "2. Care sunt 3–5 realizări cu cel mai mare impact pentru business și de ce contează?",
        "3. Unde s-a concentrat efortul echipei (zone-cheie ale platformei)?",
        "4. Ce zonă a evoluat cel mai vizibil față de nivelul anterior?",
        "5. Există semnale de risc sau de zonă fragilă (ex. multe corecturi într-o arie = instabilitate, puține commit-uri într-o zonă critică = neglijare)?",
        "",
        "## Teme majore ale lunii",
        "Identifică **3–5 teme transversale** (ex. „Automatizarea completă a pontajelor\", „Integrarea cu ANAF pentru e-Factura\", „Modernizarea aplicației mobile\"). Pentru fiecare temă emite un bullet `- **Temă:** descriere de 1–2 propoziții + impact vizibil.`",
        "",
        "## Progres pe arii funcționale",
        "Pentru fiecare arie de business care a avut activitate, emite o sub-secțiune cu:",
        "1. Un titlu `### **Nume arie**`.",
        "2. **2–3 propoziții de context** care descriu cum a evoluat aria în această lună și care este starea ei actuală.",
        "3. **5–12 bullet-uri** care grupează commit-urile similare în realizări concrete de business. Poți uni 3–8 commit-uri apropiate ca temă într-un singur bullet. Fiecare bullet = 1 propoziție, verb la timpul trecut, orientat pe impact.",
        "4. La finalul fiecărui bullet, în italics și între paranteze, enumeră SHA-urile scurte care stau la baza lui, separate prin virgulă. Poți tăia cu „…\" dacă sunt peste 6 — dar menționează numărul total. Exemplu: „Am regândit complet fluxul de concedii. _(a1b2c3d4, e5f6g7h8, … 12 commit-uri)_\".",
        "",
        "Categoriile disponibile (folosește DOAR acelea care au activitate):",
        cats,
        "",
        "## Observații strategice",
        "Închide raportul cu **2–4 bullet-uri de observații**: trend-uri vizibile, recomandări implicite bazate pe pattern-ul commit-urilor, zone în care echipa poate accelera sau care necesită atenție.",
        "",
        "REGULI DE FORMULARE:",
        "- Zero jargon tehnic. NU folosi: commit, endpoint, API, refactor, deploy, repo, PR, merge, schema, query, cache, migration, bug fix, hotfix.",
        "- Fiecare bullet începe cu un verb la timpul trecut.",
        "- Vorbește la persoana întâi plural („echipa\" / „noi\").",
        "- NU include nume de fișiere, funcții sau dezvoltatori.",
        "- NU uni arii diferite sub același titlu.",
        "- Acoperă TOATE commit-urile primite: fiecare SHA trebuie să apară măcar o dată într-un bullet.",
        "- Nu adăuga concluzie, „Cu stimă\" sau CTA.",
        "",
        "**Lungime: raport strategic lunar.** Între 900 și 1600 de cuvinte. Dens, lizibil, orientat pe valoare.",
    ]


def build_prompt(commits_by_repo: dict[str, list[dict]], period_config: dict) -> str:
    """Build the user prompt fed to Claude. Branches on detail_level."""
    window = period_config["prompt_window"]
    detail = period_config.get("detail_level", "brief")

    if detail == "comprehensive":
        lines = _build_prompt_comprehensive(window)
    elif detail == "detailed":
        lines = _build_prompt_detailed(window)
    else:
        lines = _build_prompt_brief(window)

    lines.extend(
        [
            "",
            "---",
            "",
            f"## Commit-uri brute ({window}) — sursă pentru sinteză, NU le afișa în output",
            "",
        ]
    )
    for repo, commits in commits_by_repo.items():
        lines.append(f"### {repo}")
        if not commits:
            lines.append(f"_(niciun commit {window})_")
            lines.append("")
            continue
        for c in commits:
            body = c.get("body", "").strip()
            body_line = f"\n    > {body}" if body else ""
            lines.append(
                f"- `{c['sha']}` **{c['author']}** — {c['subject']}{body_line}"
            )
        lines.append("")
    return "\n".join(lines)


def build_timesheet_section(commits_by_repo: dict[str, list[dict]]) -> str:
    """Build a per-author timesheet table for monthly reports."""
    all_commits: list[dict] = []
    for repo_name, commits in commits_by_repo.items():
        for c in commits:
            all_commits.append({**c, "repo": repo_name})

    if not all_commits:
        return ""

    by_author: dict[str, list[dict]] = {}
    for c in all_commits:
        name = c.get("author") or "necunoscut"
        by_author.setdefault(name, []).append(c)

    lines = [
        "## Raport Timesheet Lunar",
        "",
        "_Estimare pe baza istoricului Git — euristica git-hours (gap max 2h între commit-uri, buffer 2h per sesiune)._",
        "",
        "| Dezvoltator | Commit-uri | Zile active | Ore estimate |",
        "|---|---:|---:|---:|",
    ]

    total_commits = 0
    total_hours = 0.0
    total_days: set = set()

    # Sort authors by hours descending for readability
    author_rows: list[tuple[str, int, int, float]] = []
    for name, author_commits in by_author.items():
        hours = estimate_hours_worked(author_commits)
        days: set = set()
        for c in author_commits:
            try:
                days.add(datetime.fromisoformat(c["date"]).date())
            except (KeyError, ValueError):
                continue
        author_rows.append((name, len(author_commits), len(days), hours))
        total_commits += len(author_commits)
        total_hours += hours
        total_days.update(days)

    for name, commits_count, days_count, hours in sorted(
        author_rows, key=lambda r: (-r[3], r[0])
    ):
        lines.append(
            f"| {name} | {commits_count} | {days_count} | ~{hours}h |"
        )

    lines.append(
        f"| **TOTAL** | **{total_commits}** | **{len(total_days)}** | **~{round(total_hours, 1)}h** |"
    )
    lines.append("")
    return "\n".join(lines)


SYSTEM_PROMPT_BRIEF = (
    "Ești un asistent de business care redactează digest-uri ZILNICE ECHILIBRATE "
    "pentru directorul general Autoworld, pe baza muncii echipei de dezvoltare "
    "a platformei JARVIS. "
    "Publicul tău NU cunoaște termeni tehnici — traduci totul în limbaj de "
    "afaceri clar, orientat pe impact. "
    "OBIECTIV: FIECARE commit primit devine un bullet separat, formulat scurt "
    "și orientat pe valoare. NU uni commit-uri diferite într-un singur bullet, "
    "dar grupează-le pe arii funcționale ale afacerii. Zero jargon tehnic, "
    "zero umplutură, zero metacomentarii. "
    "Răspunzi DOAR cu markdown pentru corpul emailului, fără introduceri sau "
    "concluzii."
)

SYSTEM_PROMPT_DETAILED = (
    "Ești un analist de business care redactează SINTEZE SĂPTĂMÂNALE pentru "
    "directorul general Autoworld, pe baza muncii echipei de dezvoltare a "
    "platformei JARVIS. Publicul tău NU cunoaște termeni tehnici. "
    "OBIECTIV: raport săptămânal dens dar lizibil, cu sumar executiv de 4–6 "
    "propoziții, apoi câte o sub-secțiune pentru fiecare arie funcțională "
    "atinsă, cu 1–2 propoziții de context + bullet-uri care grupează commit-uri "
    "similare în realizări concrete de business. "
    "Folosești Markdown curat și respecți cu strictețe structura cerută în "
    "prompt. Zero jargon tehnic. Zero concluzii sau CTA. Răspunzi DOAR cu "
    "corpul raportului."
)

SYSTEM_PROMPT_COMPREHENSIVE = (
    "Ești un analist de business senior care redactează RAPOARTE STRATEGICE "
    "LUNARE pentru directorul general Autoworld. Raportul tău e folosit de "
    "management pentru decizii — nu e o listă de task-uri, e o narațiune "
    "structurată care explică cum a evoluat platforma JARVIS, unde s-a "
    "concentrat efortul, ce teme majore au dominat luna, ce s-a livrat cu "
    "impact pentru business și ce semnale oferă datele pentru luna următoare. "
    "Publicul tău NU cunoaște termeni tehnici — traduci totul în limbaj "
    "executiv, clar, orientat pe valoare. "
    "Respecți cu strictețe structura cerută în prompt: Sumar executiv → Teme "
    "majore → Progres pe arii funcționale (cu context + bullet-uri grupate) → "
    "Observații strategice. Folosești Markdown curat. Zero jargon tehnic, zero "
    "umplutură, zero concluzii sau CTA. Răspunzi DOAR cu corpul raportului."
)

SYSTEM_PROMPTS: dict[str, str] = {
    "brief": SYSTEM_PROMPT_BRIEF,
    "detailed": SYSTEM_PROMPT_DETAILED,
    "comprehensive": SYSTEM_PROMPT_COMPREHENSIVE,
}

MAX_TOKENS_BY_DETAIL: dict[str, int] = {
    "brief": 8192,
    "detailed": 12000,
    "comprehensive": 16000,
}


def translate_with_claude(prompt: str, detail_level: str = "brief") -> str:
    """Stream a response from Claude and return the text body.

    The system prompt and output budget scale with `detail_level`:
      - "brief"        → daily  (concise, 1 bullet per commit)
      - "detailed"     → weekly (per-area narrative + grouped bullets)
      - "comprehensive"→ monthly (strategic report with themes + observations)
    """
    client = anthropic.Anthropic()
    system = SYSTEM_PROMPTS.get(detail_level, SYSTEM_PROMPT_BRIEF)
    max_tokens = MAX_TOKENS_BY_DETAIL.get(detail_level, 8192)
    with client.messages.stream(
        model=MODEL,
        max_tokens=max_tokens,
        thinking={"type": "adaptive"},
        system=system,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        final = stream.get_final_message()

    for block in final.content:
        if block.type == "text":
            return block.text
    return ""


def markdown_to_html(md: str) -> str:
    """Small markdown → HTML converter sufficient for email rendering.

    Supports: headings, bold, inline code, bullet lists, fenced ``` blocks,
    GitHub-style pipe tables, horizontal rules, paragraphs with line breaks.
    """
    # 1. Extract fenced code blocks first (we don't escape inside them yet).
    code_blocks: list[str] = []

    def _stash_code(match: re.Match) -> str:
        code_blocks.append(match.group(1))
        return f"\x00CODEBLOCK{len(code_blocks) - 1}\x00"

    md = re.sub(r"```(?:\w+)?\n(.*?)```", _stash_code, md, flags=re.S)

    text = html.escape(md)

    # 2. Headings (### before ## before # to avoid partial matches).
    text = re.sub(r"^### (.+)$", r"<h3>\1</h3>", text, flags=re.M)
    text = re.sub(r"^## (.+)$", r"<h2>\1</h2>", text, flags=re.M)
    text = re.sub(r"^# (.+)$", r"<h1>\1</h1>", text, flags=re.M)

    # 3. Horizontal rules.
    text = re.sub(r"^---$", "<hr>", text, flags=re.M)

    # 4. Inline formatting.
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"_([^_\n]+)_", r"<em>\1</em>", text)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)

    # 5. Pipe tables. A table is a header line + separator + N body rows.
    def _render_table(match: re.Match) -> str:
        block = match.group(0).strip("\n")
        rows = [r for r in block.split("\n") if r.strip()]
        if len(rows) < 2:
            return block
        header = [c.strip() for c in rows[0].strip("|").split("|")]
        body_rows = [
            [c.strip() for c in r.strip("|").split("|")] for r in rows[2:]
        ]
        out = ["<table>", "<thead><tr>"]
        out.extend(f"<th>{h}</th>" for h in header)
        out.append("</tr></thead><tbody>")
        for r in body_rows:
            out.append("<tr>")
            out.extend(f"<td>{c}</td>" for c in r)
            out.append("</tr>")
        out.append("</tbody></table>")
        return "\n".join(out)

    text = re.sub(
        r"(?:^\|.+\|\s*$\n)(?:^\|[-: |]+\|\s*$\n)(?:^\|.+\|\s*$\n?)+",
        _render_table,
        text,
        flags=re.M,
    )

    # 6. Bullet lists.
    lines = text.split("\n")
    out: list[str] = []
    in_list = False
    for line in lines:
        m = re.match(r"^\s*[-*] (.+)$", line)
        if m:
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{m.group(1)}</li>")
        else:
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append(line)
    if in_list:
        out.append("</ul>")
    text = "\n".join(out)

    # 7. Paragraphs: wrap non-block lines.
    paragraphs = re.split(r"\n\s*\n", text)
    wrapped = []
    for p in paragraphs:
        if re.match(r"\s*<(h\d|ul|ol|p|pre|blockquote|table|hr)", p):
            wrapped.append(p)
        elif "\x00CODEBLOCK" in p:
            wrapped.append(p)
        else:
            wrapped.append(f"<p>{p.replace(chr(10), '<br>')}</p>")
    text = "\n".join(wrapped)

    # 8. Restore fenced code blocks (escaped) as <pre>.
    def _restore_code(match: re.Match) -> str:
        idx = int(match.group(1))
        return f"<pre>{html.escape(code_blocks[idx])}</pre>"

    text = re.sub(r"\x00CODEBLOCK(\d+)\x00", _restore_code, text)

    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<style>body{font-family:-apple-system,Segoe UI,Arial,sans-serif;"
        "max-width:760px;margin:0 auto;padding:24px;color:#222;line-height:1.55;}"
        "h1{border-bottom:2px solid #eee;padding-bottom:8px;}"
        "h2{margin-top:30px;color:#0b5394;border-bottom:1px solid #eee;padding-bottom:4px;}"
        "h3{margin-top:22px;color:#444;}"
        "code{background:#f4f4f4;padding:2px 6px;border-radius:3px;font-size:90%;}"
        "pre{background:#f7f7f9;border:1px solid #e1e4e8;border-radius:6px;"
        "padding:12px 16px;overflow-x:auto;font-family:Menlo,Consolas,monospace;"
        "font-size:13px;line-height:1.4;}"
        "table{border-collapse:collapse;width:100%;margin:12px 0;font-size:14px;}"
        "th,td{padding:8px 12px;border-bottom:1px solid #e1e4e8;text-align:left;}"
        "th{background:#f6f8fa;font-weight:600;}"
        "tbody tr:hover{background:#fafbfc;}"
        "hr{border:none;border-top:1px solid #e1e4e8;margin:28px 0;}"
        "li{margin:4px 0;}</style></head><body>"
        f"{text}"
        "</body></html>"
    )


def send_email(subject: str, body_markdown: str, recipients: str = _BASE_RECIPIENTS) -> None:
    host = os.environ.get("SMTP_HOST", "smtp.office365.com")
    port = int(os.environ.get("SMTP_PORT", "587") or "587")
    username = os.environ["SMTP_USERNAME"]
    password = os.environ["SMTP_PASSWORD"]
    from_email = os.environ.get("SMTP_FROM_EMAIL") or username
    from_name = os.environ.get("SMTP_FROM_NAME", "JARVIS Digest")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{from_name} <{from_email}>"
    override = os.getenv("DIGEST_RECIPIENTS")
    effective = override if override else recipients
    to_list = [r.strip() for r in effective.split(",") if r.strip()]
    msg["To"] = ", ".join(to_list)

    msg.attach(MIMEText(body_markdown, "plain", "utf-8"))
    msg.attach(MIMEText(markdown_to_html(body_markdown), "html", "utf-8"))

    if port == 465:
        # Implicit TLS
        with smtplib.SMTP_SSL(host, port) as server:
            server.login(username, password)
            server.send_message(msg)
    else:
        # STARTTLS (port 587 for Office365 / most corporate SMTP)
        with smtplib.SMTP(host, port) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(username, password)
            server.send_message(msg)


def main() -> int:
    period, period_config = get_period()

    # Guard: only run at the correct day/hour for this period (cron fires at
    # 05 UTC and 06 UTC to cover both EEST summer and EET winter).
    if os.environ.get("FORCE_RUN") != "1" and not should_run(period):
        now = datetime.now(ROMANIA_TZ)
        print(
            f"Not the right moment for {period} digest "
            f"(now={now:%a %d %b %H:%M %Z}). Skipping."
        )
        return 0

    commits_by_repo: dict[str, list[dict]] = {}
    stats_by_repo: dict[str, dict[str, dict]] = {}
    for repo in REPOS:
        name = repo["name"]
        path = os.environ.get(repo["env"], repo["default"])
        if not os.path.isdir(os.path.join(path, ".git")):
            print(f"Skipping {name}: {path!r} is not a git repo", file=sys.stderr)
            commits_by_repo[name] = []
            stats_by_repo[name] = {}
            continue
        commits_by_repo[name] = collect_commits(path, period_config["git_since"])
        # numstat is only needed for the stats section (weekly/monthly).
        if period_config.get("include_stats"):
            try:
                stats_by_repo[name] = collect_commit_stats(
                    path, period_config["git_since"]
                )
            except subprocess.CalledProcessError as exc:
                print(
                    f"Warning: numstat failed for {name}: {exc}",
                    file=sys.stderr,
                )
                stats_by_repo[name] = {}
        else:
            stats_by_repo[name] = {}

    total = sum(len(cs) for cs in commits_by_repo.values())
    all_commits = [c for cs in commits_by_repo.values() for c in cs]
    hours_worked = estimate_hours_worked(all_commits)

    now_ro = datetime.now(ROMANIA_TZ)
    date_str = format_ro_date(now_ro)
    title = period_config["title"]
    period_desc = period_config["period_desc_ro"]

    if total == 0:
        body = (
            f"# {title} — {date_str}\n\n"
            f"Niciun commit nou în {period_desc} în repo-urile **JARVIS** sau **jarvis-mobile**.\n\n"
            "_Perioadă liniștită. Spor la treabă!_"
        )
    else:
        prompt = build_prompt(commits_by_repo, period_config)
        try:
            ai_body = translate_with_claude(
                prompt, detail_level=period_config.get("detail_level", "brief")
            )
        except anthropic.APIError as exc:
            print(f"Claude API error: {exc}", file=sys.stderr)
            # Fall back to raw commits in case of API failure so the digest
            # still goes out.
            ai_body = f"_(Traducere AI indisponibilă: {exc}. Mai jos lista brută.)_\n\n{prompt}"

        header = (
            f"# {title} — {date_str}\n\n"
            f"_{period_desc.capitalize()} • {total} commit-uri • ~{hours_worked}h lucrate_\n\n"
        )

        sections: list[str] = [header]

        if period_config.get("include_stats"):
            stats_md = build_stats_section(commits_by_repo, stats_by_repo, period_config)
            if stats_md:
                sections.append(stats_md)
                sections.append("---\n")

        if period_config.get("include_timesheet"):
            timesheet_md = build_timesheet_section(commits_by_repo)
            if timesheet_md:
                sections.append(timesheet_md)
                sections.append("---\n")

        sections.append(ai_body)
        body = "\n".join(sections)

    subject = f"[JARVIS] {period_config['subject_prefix']} — {date_str} ({total})"
    period_recipients = period_config.get("recipients", _BASE_RECIPIENTS)
    send_email(subject, body, recipients=period_recipients)
    effective = os.getenv("DIGEST_RECIPIENTS") or period_recipients
    print(f"Sent {period} digest with {total} commits to {effective}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
