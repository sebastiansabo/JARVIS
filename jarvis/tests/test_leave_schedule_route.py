import core.connectors.connecteam.routes as routes


def test_route_is_wired():
    assert hasattr(routes, 'get_leave_schedule_route')
