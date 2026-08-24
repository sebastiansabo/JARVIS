#!/usr/bin/env python3
"""Happy Phase 0 — automated codebase & database assessment.

Read-only. Produces the raw material for docs/happy/HAPPY_ASSESSMENT.md so that
every later agent works from verified facts instead of assumptions.

Usage:
    python3 scripts/happy_assess.py --repo . --out docs/happy/HAPPY_ASSESSMENT_RAW.md
    python3 scripts/happy_assess.py --repo . --db "$DATABASE_URL" --out docs/happy/HAPPY_ASSESSMENT_RAW.md

The --db pass is optional and strictly SELECT-only. Prefer read-only credentials.
"""

import argparse
import ast
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

# ── What we expect to find. Each entry is a hypothesis Phase 0 must confirm. ──

EXPECTED_FILES = [
    ("push pipeline",            "jarvis/core/notifications/push_service.py"),
    ("in-app notify helper",     "jarvis/core/notifications/notify.py"),
    ("in-app notif repo",        "jarvis/core/notifications/repositories/in_app_repo.py"),
    ("notification routes",      "jarvis/core/notifications/routes.py"),
    ("base repository",          "jarvis/core/base_repository.py"),
    ("migration entry point",    "jarvis/migrations/init_schema.py"),
    ("roles/permissions schema", "jarvis/migrations/domains/schema_roles.py"),
    ("hr schema (schema idiom)", "jarvis/migrations/domains/schema_hr.py"),
    ("permission decorators",    "jarvis/core/roles/decorators.py"),
    ("mobile shared/jwt",        "jarvis/core/mobile/routes/_shared.py"),
    ("mobile dashboard",         "jarvis/core/mobile/routes/dashboard.py"),
    ("media proxy",              "jarvis/core/media/routes.py"),
    ("deeplink",                 "jarvis/core/deeplink/routes.py"),
    ("digest/chat blueprint",    "jarvis/chat/routes.py"),
    ("digest schema",            "jarvis/migrations/domains/schema_digest.py"),
    ("app factory",              "jarvis/app.py"),
    ("scheduler",                "jarvis/tasks/cleanup.py"),
    ("frontend api client",      "jarvis/frontend/src/api/client.ts"),
    ("dashboard widgets",        "jarvis/frontend/src/pages/Dashboard/widgets.tsx"),
    ("dashboard widget types",   "jarvis/frontend/src/pages/Dashboard/types.ts"),
    ("dashboard prefs",          "jarvis/frontend/src/pages/Dashboard/useDashboardPrefs.ts"),
    ("hub page",                 "jarvis/frontend/src/pages/Hub/index.tsx"),
    ("app router",               "jarvis/frontend/src/App.tsx"),
    ("frontend package.json",    "jarvis/frontend/package.json"),
    ("pytest conftest",          "jarvis/conftest.py"),
    ("playwright config",        "playwright.config.js"),
]

# Functions whose exact signature later agents will call.
SIGNATURES_WANTED = {
    "jarvis/core/notifications/push_service.py": ["send_push_to_users", "send_push_to_user"],
    "jarvis/core/notifications/notify.py":       ["notify_user", "notify_users", "notify_with_push"],
    "jarvis/core/base_repository.py":            ["query_all", "query_one", "execute", "execute_many", "transaction"],
    "jarvis/core/mobile/routes/_shared.py":      ["jwt_required", "_current_mobile_user", "_user_json"],
    "jarvis/core/roles/decorators.py":           ["*"],
}

# shadcn primitives the Happy UI needs.
UI_COMPONENTS_NEEDED = [
    "dialog", "drawer", "sheet", "badge", "checkbox", "card", "button",
    "skeleton", "progress", "tabs", "select", "textarea", "avatar", "separator",
]

# Name collisions that would force a rename before Phase 1.
COLLISION_TOKENS = ["campaign", "announcement", "banner", "kudos", "pulse", "happy", "spotlight", "marquee", "digest"]

# Tables Happy expects to read from.
DB_TABLES_EXPECTED = [
    "public.users", "public.roles", "public.notifications", "public.mobile_devices",
    "public.permissions_v2", "public.role_permissions_v2", "public.department_structure",
    "public.structure_nodes", "hr.events", "public.digest_channels", "public.digest_posts",
    "public.digest_read_status", "public.hr_dept_pulse_votes",
]

TARGETING_COLUMNS = ["company", "brand", "department", "subdepartment", "org_unit_id", "contract_status", "is_active"]


# ── helpers ──────────────────────────────────────────────────────────────────

def sh(cmd, cwd=None):
    try:
        return subprocess.run(cmd, cwd=cwd, shell=True, capture_output=True, text=True, timeout=60).stdout.strip()
    except Exception as e:
        return f"<error: {e}>"


def rel(repo, path):
    return os.path.join(repo, path)


def read(path, limit=None):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read(limit) if limit else f.read()
    except Exception:
        return None


def py_signatures(src, wanted):
    """Extract def signatures from a python source string."""
    out = []
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        return [f"!! parse error: {e}"]
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if wanted != ["*"] and node.name not in wanted:
                continue
            a = node.args
            parts = []
            defaults = [None] * (len(a.args) - len(a.defaults)) + list(a.defaults)
            for arg, d in zip(a.args, defaults):
                if d is None:
                    parts.append(arg.arg)
                else:
                    try:
                        parts.append(f"{arg.arg}={ast.unparse(d)}")
                    except Exception:
                        parts.append(f"{arg.arg}=<?>")
            if a.vararg:
                parts.append("*" + a.vararg.arg)
            for arg, d in zip(a.kwonlyargs, a.kw_defaults):
                parts.append(f"{arg.arg}={ast.unparse(d) if d is not None else '<req>'}")
            if a.kwarg:
                parts.append("**" + a.kwarg.arg)
            out.append(f"L{node.lineno}: def {node.name}({', '.join(parts)})")
    return out


def find_tables(repo):
    """All CREATE TABLE names declared in migrations."""
    tables = {}
    mig = rel(repo, "jarvis/migrations")
    for root, _, files in os.walk(mig):
        for fn in files:
            if not fn.endswith(".py"):
                continue
            p = os.path.join(root, fn)
            src = read(p) or ""
            for m in re.finditer(r"CREATE TABLE IF NOT EXISTS\s+([\w.]+)", src, re.I):
                tables.setdefault(m.group(1), []).append(
                    f"{os.path.relpath(p, repo)}:{src[:m.start()].count(chr(10)) + 1}")
    return tables


def find_routes(repo):
    """All Flask route decorators, grouped by blueprint file."""
    routes = []
    for root, dirs, files in os.walk(rel(repo, "jarvis")):
        dirs[:] = [d for d in dirs if d not in ("node_modules", "__pycache__", "venv", ".git", "frontend")]
        for fn in files:
            if not fn.endswith(".py"):
                continue
            p = os.path.join(root, fn)
            src = read(p) or ""
            for m in re.finditer(r"@(\w+)\.route\(\s*['\"]([^'\"]+)['\"]", src):
                routes.append((m.group(1), m.group(2), os.path.relpath(p, repo)))
    return routes


def h(title, level=2):
    return f"\n{'#' * level} {title}\n"


# ── report sections ──────────────────────────────────────────────────────────

def section_meta(repo):
    o = [h("0. Run metadata")]
    o.append(f"- Generated: `{datetime.now(timezone.utc).isoformat()}`")
    o.append(f"- Repo: `{os.path.abspath(repo)}`")
    o.append(f"- Commit: `{sh('git rev-parse --short HEAD', repo)}`")
    o.append(f"- Branch: `{sh('git rev-parse --abbrev-ref HEAD', repo)}`")
    dirty = sh("git status --porcelain", repo)
    o.append(f"- Working tree: {'DIRTY — commit or stash before Phase 1' if dirty else 'clean'}")
    o.append(f"- Python: `{sys.version.split()[0]}`")
    return "\n".join(o)


def section_files(repo):
    o = [h("1. Expected integration points")]
    o.append("| Claim | Path | Status | Lines |")
    o.append("|---|---|---|---|")
    missing = []
    for label, path in EXPECTED_FILES:
        full = rel(repo, path)
        if os.path.isfile(full):
            n = sum(1 for _ in open(full, "r", encoding="utf-8", errors="replace"))
            o.append(f"| {label} | `{path}` | FOUND | {n} |")
        else:
            o.append(f"| {label} | `{path}` | **MISSING** | — |")
            missing.append(path)
    if missing:
        o.append(f"\n> **{len(missing)} expected file(s) missing.** The spec's §3 assumptions do not hold. "
                 "Resolve before Phase 1: " + ", ".join(f"`{m}`" for m in missing))
    return "\n".join(o)


def section_signatures(repo):
    o = [h("2. Verified function signatures"),
         "These are the exact contracts later agents must call. Copy them into HAPPY_ASSESSMENT.md §2."]
    for path, wanted in SIGNATURES_WANTED.items():
        full = rel(repo, path)
        o.append(f"\n**`{path}`**\n")
        src = read(full)
        if src is None:
            o.append("```\nFILE NOT FOUND\n```")
            continue
        sigs = py_signatures(src, wanted)
        o.append("```python")
        o.extend(sigs if sigs else ["<none of the expected functions found>"])
        o.append("```")
        if wanted != ["*"]:
            found = {s.split("def ")[1].split("(")[0] for s in sigs if "def " in s}
            for w in wanted:
                if w not in found:
                    o.append(f"> `{w}` NOT FOUND — spec assumption invalid.")
    return "\n".join(o)


def section_schema(repo):
    o = [h("3. Declared database tables (from migrations)")]
    tables = find_tables(repo)
    o.append(f"Total declared: **{len(tables)}**\n")
    schemas = {}
    for t in sorted(tables):
        schemas.setdefault(t.split(".")[0] if "." in t else "public", []).append(t)
    for s in sorted(schemas):
        o.append(f"- **{s}** ({len(schemas[s])}): " + ", ".join(f"`{t}`" for t in sorted(schemas[s])))
    o.append(h("3.1 Name collisions with Happy", 3))
    o.append("| Token | Colliding tables |")
    o.append("|---|---|")
    for tok in COLLISION_TOKENS:
        hits = [t for t in tables if tok in t.lower()]
        o.append(f"| `{tok}` | {', '.join('`'+x+'`' for x in hits) if hits else 'none'} |")
    o.append(h("3.2 Non-public schema idiom (copy this for `happy`)", 3))
    hrsrc = read(rel(repo, "jarvis/migrations/domains/schema_hr.py")) or ""
    m = re.search(r"CREATE SCHEMA[^\n]*", hrsrc, re.I)
    o.append("```sql\n" + (m.group(0) if m else "<no CREATE SCHEMA found — check how the hr schema is created>") + "\n```")
    o.append(h("3.3 Migration registration point", 3))
    init = read(rel(repo, "jarvis/migrations/init_schema.py")) or ""
    calls = re.findall(r"^\s*(?:from|import|.*create_schema_\w+|.*create_\w+_schema)\(.*$", init, re.M)
    o.append("Lines in `init_schema.py` that invoke a domain schema builder "
             "(register `create_schema_happy` alongside these):\n")
    o.append("```python")
    o.extend(calls[:60] if calls else ["<pattern not detected — read init_schema.py manually>"])
    o.append("```")
    return "\n".join(o)


def section_routes(repo):
    o = [h("4. Route surface")]
    routes = find_routes(repo)
    o.append(f"Total Flask routes declared: **{len(routes)}**\n")
    bps = {}
    for bp, path, f in routes:
        bps.setdefault(bp, []).append(path)
    o.append("| Blueprint | Routes | Example |")
    o.append("|---|---|---|")
    for bp in sorted(bps, key=lambda b: -len(bps[b])):
        o.append(f"| `{bp}` | {len(bps[bp])} | `{sorted(bps[bp])[0]}` |")
    o.append(h("4.1 Prefix collisions", 3))
    for pref in ["/api/happy", "/api/mobile/happy", "/go/happy"]:
        hits = [f"`{p}`" for _, p, _ in routes if p.startswith(pref)]
        o.append(f"- `{pref}` → {'COLLISION: ' + ', '.join(hits) if hits else 'free'}")
    o.append(h("4.2 Mobile route inventory", 3))
    mob = sorted({p for _, p, _ in routes if p.startswith("/api/mobile")})
    o.append("```")
    o.extend(mob if mob else ["<none>"])
    o.append("```")
    return "\n".join(o)


def section_frontend(repo):
    o = [h("5. Frontend")]
    pkg = read(rel(repo, "jarvis/frontend/package.json")) or "{}"
    o.append(h("5.1 Dependencies present (no new packages without approval)", 3))
    for dep in ["react", "@tanstack/react-query", "radix-ui", "lucide-react", "react-markdown",
                "remark-gfm", "sonner", "zustand", "react-hook-form", "zod", "tailwindcss",
                "react-grid-layout", "recharts", "next-themes"]:
        needle = '"' + dep + '"'
        o.append("- `%s`: %s" % (dep, "PRESENT" if needle in pkg else "**ABSENT**"))
    o.append(h("5.2 shadcn/ui primitives", 3))
    uidir = rel(repo, "jarvis/frontend/src/components/ui")
    have = set()
    if os.path.isdir(uidir):
        have = {f.rsplit(".", 1)[0] for f in os.listdir(uidir)}
    o.append("| Component | Status |")
    o.append("|---|---|")
    for c in UI_COMPONENTS_NEEDED:
        o.append(f"| `{c}` | {'present' if c in have else '**must add: npx shadcn add ' + c + '**'} |")
    o.append(h("5.3 Dashboard widget registry", 3))
    for p in ["jarvis/frontend/src/pages/Dashboard/types.ts",
              "jarvis/frontend/src/pages/Dashboard/useDashboardPrefs.ts"]:
        src = read(rel(repo, p))
        o.append(f"\n`{p}`:\n```ts")
        o.append((src[:1600] if src else "<not found>"))
        o.append("```")
    o.append(h("5.4 Hub insertion point", 3))
    hub = read(rel(repo, "jarvis/frontend/src/pages/Hub/index.tsx")) or ""
    for i, line in enumerate(hub.splitlines(), 1):
        if re.search(r"Right 1/3|Notifications|HubWorkSummaryCard|HubBonusCard|HubAppsCard", line):
            o.append(f"- L{i}: `{line.strip()[:110]}`")
    o.append("\n> Insert `<MarqueeWidget placement=\"hub_card\" />` immediately above the Notifications "
             "`<Card>` in the right column. Touch nothing else in this file.")
    o.append(h("5.5 i18n strategy", 3))
    src_dir = rel(repo, "jarvis/frontend/src")
    i18n_hits = sh(f"grep -rl \"react-i18next\\|i18next\\|useTranslation\" {src_dir} 2>/dev/null | head -5")
    o.append(f"i18n library references: {i18n_hits or 'NONE FOUND'}")
    o.append("> If none: campaign content is single-locale. Store `locale` on the campaign anyway; "
             "do not build a translation layer in Phase 1.")
    return "\n".join(o)


def section_scheduler(repo):
    o = [h("6. Background jobs")]
    src = read(rel(repo, "jarvis/tasks/cleanup.py")) or ""
    o.append("Registration idiom for the Happy nightly jobs "
             "(`refresh_targets`, `purge_events`, `rollup_stats`, `expire_points`):\n")
    o.append("```python")
    lines = [l for l in src.splitlines() if re.search(r"add_job|scheduler|cron|interval|def start_scheduler", l)]
    o.extend(lines[:40] if lines else ["<no scheduler pattern detected — read tasks/ manually>"])
    o.append("```")
    return "\n".join(o)


def section_tests(repo):
    o = [h("7. Test conventions")]
    tdir = rel(repo, "jarvis/tests")
    if os.path.isdir(tdir):
        subs = sorted(d for d in os.listdir(tdir) if os.path.isdir(os.path.join(tdir, d)))
        n = int(sh(f"find {tdir} -name 'test_*.py' | wc -l") or 0)
        o.append(f"- pytest files: **{n}**, subdirectories: {', '.join(subs) or '(flat)'}")
    conf = read(rel(repo, "jarvis/conftest.py")) or ""
    fixtures = re.findall(r"@pytest\.fixture[^\n]*\ndef (\w+)", conf)
    o.append(f"- conftest fixtures: {', '.join('`'+f+'`' for f in fixtures) or '<none detected>'}")
    n_vitest = int(sh(f"find {rel(repo,'jarvis/frontend/src')} -name '*.test.ts*' -not -path '*node_modules*' | wc -l") or 0)
    o.append(f"- vitest files: **{n_vitest}**")
    o.append(f"- playwright config: {'present' if os.path.isfile(rel(repo,'playwright.config.js')) else 'MISSING'}")
    return "\n".join(o)


def section_db(dsn):
    o = [h("8. Production data reality")]
    if not dsn:
        o.append("_Skipped — no `--db` given. **This section is required before Phase 1.** "
                 "Targeting-column null rates and department sizes determine whether audience "
                 "targeting and pulse cohorts work at all._")
        return "\n".join(o)
    try:
        import psycopg2
        import psycopg2.extras
    except ImportError:
        o.append("_psycopg2 not installed in this environment._")
        return "\n".join(o)
    try:
        conn = psycopg2.connect(dsn)
        conn.set_session(readonly=True, autocommit=True)
    except Exception as e:
        o.append(f"_Connection failed: {e}_")
        return "\n".join(o)

    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    def q(sql, params=None):
        try:
            cur.execute(sql, params or ())
            return cur.fetchall()
        except Exception as e:
            return [{"error": str(e)}]

    o.append(h("8.1 Expected tables present", 3))
    o.append("| Table | Present | Rows |")
    o.append("|---|---|---|")
    for t in DB_TABLES_EXPECTED:
        schema, name = t.split(".") if "." in t else ("public", t)
        r = q("SELECT to_regclass(%s) AS reg", (f"{schema}.{name}",))
        present = bool(r and r[0].get("reg"))
        cnt = "—"
        if present:
            c = q(f'SELECT COUNT(*) AS n FROM {schema}."{name}"')
            cnt = c[0].get("n", "?") if c else "?"
        o.append(f"| `{t}` | {'yes' if present else '**NO**'} | {cnt} |")

    o.append(h("8.2 Targeting-column coverage on users (active only)", 3))
    o.append("| Column | Non-null | % of active | Distinct |")
    o.append("|---|---|---|---|")
    tot = q("SELECT COUNT(*) AS n FROM users WHERE is_active")
    total = (tot[0].get("n") or 0) if tot else 0
    for col in TARGETING_COLUMNS:
        if col == "is_active":
            continue
        r = q(f'SELECT COUNT("{col}") AS nn, COUNT(DISTINCT "{col}") AS d FROM users WHERE is_active')
        if r and "error" in r[0]:
            o.append(f"| `{col}` | error: {r[0]['error'][:60]} | | |")
            continue
        nn = r[0].get("nn", 0) if r else 0
        d = r[0].get("d", 0) if r else 0
        pct = f"{(100.0 * nn / total):.0f}%" if total else "—"
        warn = " ⚠️" if total and nn / total < 0.8 else ""
        o.append(f"| `{col}` | {nn} | {pct}{warn} | {d} |")
    o.append(f"\nActive users: **{total}**")
    o.append("> Any column below 80% coverage cannot be used as a primary audience dimension "
             "without a data-cleanup task in Phase 1.")

    o.append(h("8.3 Department sizes — drives the pulse anonymity rollup", 3))
    rows = q("""SELECT COALESCE(department,'(null)') AS dept, COUNT(*) AS n
                FROM users WHERE is_active GROUP BY 1 ORDER BY 2 ASC""")
    small = [r for r in rows if isinstance(r.get("n"), int) and r["n"] < 5]
    o.append(f"- Departments: **{len(rows)}**")
    o.append(f"- **Below the min_group_size of 5: {len(small)}** → these cohorts must roll up to their parent unit")
    if small:
        o.append("\n| Department | Active |")
        o.append("|---|---|")
        for r in small[:25]:
            o.append(f"| {r['dept']} | {r['n']} |")

    o.append(h("8.4 Push reach ceiling", 3))
    d = q("SELECT COUNT(*) AS devices, COUNT(DISTINCT user_id) AS users FROM mobile_devices")
    if d and "error" not in d[0]:
        du = d[0].get("users") or 0
        o.append(f"- Registered devices: **{d[0].get('devices')}** across **{du}** users")
        if total:
            o.append(f"- Push-reachable share of active users: **{100.0*du/total:.0f}%** "
                     "— this is the hard ceiling on any push-based KPI")
    else:
        o.append("- `mobile_devices` unreadable or absent")

    o.append(h("8.5 hr.events volume (auto-generated event campaigns)", 3))
    e = q("SELECT COUNT(*) AS n, MIN(start_date) AS first, MAX(start_date) AS last FROM hr.events")
    if e and "error" not in e[0]:
        o.append(f"- rows: {e[0].get('n')}, range {e[0].get('first')} → {e[0].get('last')}")
    else:
        o.append("- hr.events unreadable or absent")

    conn.close()
    return "\n".join(o)


def section_verdict():
    return (h("9. Verdict — fill this in by hand") +
            "\n| Integration point | GO / GO-WITH-CHANGES / NO-GO | Evidence | Note |\n"
            "|---|---|---|---|\n"
            "| Push pipeline reuse | | | |\n"
            "| Permissions v2 seeding | | | |\n"
            "| Mobile payload extension | | | |\n"
            "| Media upload + proxy | | | |\n"
            "| Dashboard widget slot | | | |\n"
            "| Hub slot | | | |\n"
            "| Nightly job registration | | | |\n"
            "| Audience targeting data quality | | | |\n"
            "| Pulse cohort viability | | | |\n"
            "| i18n strategy | | | |\n"
            "\n**Phase 1 may / may not begin.**\n")


def main():
    ap = argparse.ArgumentParser(description="Happy Phase 0 assessment (read-only).")
    ap.add_argument("--repo", default=".", help="repo root")
    ap.add_argument("--db", default=os.environ.get("DATABASE_URL"), help="postgres DSN (read-only preferred)")
    ap.add_argument("--out", default="docs/happy/HAPPY_ASSESSMENT_RAW.md")
    args = ap.parse_args()

    repo = os.path.abspath(args.repo)
    parts = [
        "# Happy Phase 0 — Automated Assessment (raw)",
        "\n_Generated by `scripts/happy_assess.py`. Read-only. "
        "Use this as the input to `docs/happy/HAPPY_ASSESSMENT.md`, not as a replacement for it._",
        section_meta(repo),
        section_files(repo),
        section_signatures(repo),
        section_schema(repo),
        section_routes(repo),
        section_frontend(repo),
        section_scheduler(repo),
        section_tests(repo),
        section_db(args.db),
        section_verdict(),
    ]
    report = "\n".join(parts) + "\n"

    out = args.out if os.path.isabs(args.out) else os.path.join(repo, args.out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"Wrote {out} ({len(report.splitlines())} lines)")
    if not args.db:
        print("WARNING: no --db given. Section 8 is empty and Phase 1 must not begin without it.")


if __name__ == "__main__":
    main()
