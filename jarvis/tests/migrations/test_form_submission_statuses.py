import re, pathlib

INCR = pathlib.Path(__file__).parent.parent.parent / 'migrations/domains/schema_incremental.py'
FORMS = pathlib.Path(__file__).parent.parent.parent / 'migrations/domains/schema_forms.py'
INCR = INCR.read_text()
FORMS = FORMS.read_text()

def test_incremental_adds_new_leave_statuses():
    # the idempotent re-add block must list both new statuses
    block = INCR[INCR.index('form_submissions_status_check'):]
    assert 'cancellation_pending' in block[:600]
    assert "'cancelled'" in block[:600]

def test_forms_create_and_readd_include_new_statuses():
    for m in re.finditer(r"status IN \(([^)]*)\)", FORMS):
        grp = m.group(1)
        if 'flagged' in grp:  # the form_submissions status check
            assert 'cancelled' in grp and 'cancellation_pending' in grp
