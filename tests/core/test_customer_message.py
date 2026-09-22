import core.messaging.customer_message as cm

def test_email_channel_skips_global_cc(monkeypatch):
    captured = {}
    def fake_send_email(to_email, subject, html_body, text_body=None, **kw):
        captured.update(to=to_email, skip=kw.get('skip_global_cc'))
        return True, ''
    monkeypatch.setattr(cm, 'send_email', fake_send_email)
    ok, err = cm.send_customer_message('email', 'p@ex.com', 'Subj', '<b>hi</b>')
    assert ok and captured['to'] == 'p@ex.com' and captured['skip'] is True

def test_unknown_channel():
    ok, err = cm.send_customer_message('sms', '+40721', 'S', 'B')
    assert not ok and 'unsupported' in err
