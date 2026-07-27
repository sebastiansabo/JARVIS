from core.deeplink.routes import resolve_deeplink

IPHONE = 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit'
DESKTOP = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15) AppleWebKit'


WEB = '/app/hub?module=hr&hrtab=leave-approvals'


def test_desktop_redirects_to_hub_approvals_tab():
    assert resolve_deeplink(DESKTOP, 5) == ('redirect', WEB)


def test_mobile_gets_interstitial_app_url():
    kind, url = resolve_deeplink(IPHONE, 5)
    assert kind == 'interstitial'
    assert url == 'com.jarvis.mobile2://approvals?request=5'


def test_missing_user_agent_defaults_to_web():
    assert resolve_deeplink('', 9) == ('redirect', WEB)
