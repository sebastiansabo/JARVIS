"""Praise anti-gaming rules (spec §7.4).

Pure helpers + shared constants. Count-based checks (monthly cap, reciprocity,
burst, deadline-dump) run in the repository against the DB; the numeric thresholds
and the duplicate-text detector live here so they are unit-testable.

STUB — implementation follows the failing tests (TDD).
"""

MIN_NOTE_LEN = 40                     # mandatory written note (verbal recognition d=+0.33)
MONTHLY_ALLOWANCE = 100               # giveable points granted each month
DEFAULT_KUDOS_POINTS = 10            # points transferred per kudos (giver -> recipient)
MAX_PER_RECIPIENT_PER_MONTH = 3      # rule 1: 4th to same recipient blocked
RECIPROCITY_LIMIT = 4                 # rule 2: A<->B exchanges in 60 days
RECIPROCITY_WINDOW_DAYS = 60
BURST_LIMIT = 8                       # rule 3: kudos from one giver in 60 min
BURST_WINDOW_MIN = 60
DEADLINE_DUMP_PCT = 0.5              # rule 5: >50% of allowance in final 48h
DUPLICATE_THRESHOLD = 0.9            # rule 4: similarity vs giver's last 10 notes


from difflib import SequenceMatcher


def _norm(s):
    return " ".join((s or "").lower().split())


def text_similarity(a, b):
    """Normalized (case/whitespace-insensitive) similarity ratio in [0, 1]."""
    return SequenceMatcher(None, _norm(a), _norm(b)).ratio()


def is_duplicate_note(note, recent_notes, threshold=DUPLICATE_THRESHOLD):
    """True if `note` is > threshold similar to any of the giver's recent notes."""
    return any(text_similarity(note, prev) > threshold for prev in (recent_notes or []))
