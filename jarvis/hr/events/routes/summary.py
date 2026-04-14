from ._shared import *


# ============== Summary/Stats Routes ==============

@events_bp.route('/api/summary', methods=['GET'])
@login_required
@hr_required
def api_get_summary():
    """API: Get summary statistics."""
    year = request.args.get('year', type=int)
    summary = get_event_bonuses_summary(year=year)
    return jsonify(summary)


@events_bp.route('/api/summary/by-month', methods=['GET'])
@login_required
@hr_required
def api_get_by_month():
    """API: Get bonuses grouped by month."""
    year = request.args.get('year', type=int, default=2025)
    data = get_bonuses_by_month(year)
    return jsonify(data)


@events_bp.route('/api/summary/by-employee', methods=['GET'])
@login_required
@hr_required
def api_get_by_employee():
    """API: Get bonuses grouped by employee."""
    year = request.args.get('year', type=int)
    month = request.args.get('month', type=int)
    data = get_bonuses_by_employee(year=year, month=month)
    return jsonify(data)


@events_bp.route('/api/summary/by-event', methods=['GET'])
@login_required
@hr_required
def api_get_by_event():
    """API: Get bonuses grouped by event."""
    year = request.args.get('year', type=int)
    month = request.args.get('month', type=int)
    data = get_bonuses_by_event(year=year, month=month)
    return jsonify(data)
