"""Unit tests for render_confirmation_email — the confirmation-email subject/body
builder with optional staff overrides + merge tags. Pure (no DB), so it runs under
the suite's default psycopg2 mock without a real database."""
from marketing.services.td_booking_service import render_confirmation_email

CONFIRM = 'https://x/td/confirm?token=abc'
CANCEL = 'https://x/td/cancel?token=def'
ONE = ['Audi A4 · 25.09.2026, 14:00']
TWO = ['Audi A4 · 25.09.2026, 14:00', 'BMW X5 · 25.09.2026, 15:30']


def test_default_subject_and_body_single():
    subject, body = render_confirmation_email(
        name='Ana', booked_lines=ONE, confirm_link=CONFIRM, cancel_link=CANCEL)
    assert subject == 'Confirmă programarea la test drive'
    assert 'Bună, Ana!' in body
    assert 'programarea la test drive' in body
    assert CONFIRM in body and CANCEL in body


def test_default_body_group_is_plural():
    _, body = render_confirmation_email(
        name='Ana', booked_lines=TWO, confirm_link=CONFIRM, cancel_link=CANCEL)
    assert 'cele 2 programări la test drive' in body


def test_custom_overrides_and_merge_tags():
    subject, body = render_confirmation_email(
        name='Ana', booked_lines=TWO, confirm_link=CONFIRM, cancel_link=CANCEL,
        email_subject='Salut {nume}!',
        email_body='<p>Bună {nume}, ai ales:</p><p>{programari}</p><p>{link} sau {anulare}</p>')
    assert subject == 'Salut Ana!'
    assert 'Bună Ana, ai ales:' in body
    assert 'Audi A4 · 25.09.2026, 14:00<br>BMW X5 · 25.09.2026, 15:30' in body
    assert CONFIRM in body and CANCEL in body
    # Every merge tag must be consumed.
    for tag in ('{nume}', '{programari}', '{link}', '{anulare}'):
        assert tag not in body


def test_custom_body_escapes_customer_name():
    _, body = render_confirmation_email(
        name='<script>x</script>', booked_lines=[], confirm_link=CONFIRM, cancel_link=CANCEL,
        email_body='<p>{nume}</p>')
    assert '<script>' not in body
    assert '&lt;script&gt;' in body


def test_blank_overrides_fall_back_to_default():
    subject, body = render_confirmation_email(
        name='Ana', booked_lines=ONE, confirm_link=CONFIRM, cancel_link=CANCEL,
        email_subject='   ', email_body='  ')
    assert subject == 'Confirmă programarea la test drive'
    assert 'Bună, Ana!' in body


def test_custom_subject_merges_name_and_strips_newlines():
    subject, _ = render_confirmation_email(
        name='Ana\r\nBcc: evil@x', booked_lines=ONE, confirm_link=CONFIRM, cancel_link=CANCEL,
        email_subject='Salut {nume}!')
    # {nume} is merged into the subject, but CR/LF are neutralized so a crafted
    # name can't inject extra email headers.
    assert '\r' not in subject and '\n' not in subject
    assert subject.startswith('Salut Ana')


def test_programari_html_escapes_label_content():
    _, body = render_confirmation_email(
        name='Ana', booked_lines=['A&B <X> · 25.09.2026, 14:00'],
        confirm_link=CONFIRM, cancel_link=CANCEL,
        email_body='<p>{programari}</p>')
    assert 'A&amp;B &lt;X&gt;' in body
    assert '<X>' not in body


def test_name_that_looks_like_a_tag_is_not_expanded():
    # A customer literally named '{link}' must NOT expand into a confirm anchor:
    # {nume} is substituted last, so it stays inert text.
    _, body = render_confirmation_email(
        name='{link}', booked_lines=[], confirm_link=CONFIRM, cancel_link=CANCEL,
        email_body='<p>Bună {nume}</p>')
    assert 'Bună {link}' in body
    assert CONFIRM not in body  # no anchor was injected via the name


def test_empty_booked_lines_default_body_is_singular_wording():
    # Degenerate (no lines) still renders a coherent default body.
    _, body = render_confirmation_email(
        name='Ana', booked_lines=[], confirm_link=CONFIRM, cancel_link=CANCEL)
    assert 'cele 0 programări' in body
