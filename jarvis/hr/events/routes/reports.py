"""HR Reports endpoints — aggregated company-level analytics."""

from ._shared import *


@events_bp.route('/api/reports/weekly-digest', methods=['GET'])
@login_required
@hr_required
def api_weekly_digest():
    """Return the HR weekly digest data as JSON."""
    from tasks.hr_attendance import compute_hr_weekly_report_data

    ref_str = request.args.get('reference_date')
    ref_date = date.fromisoformat(ref_str) if ref_str else None
    period = request.args.get('period')  # today, week, month, quarter, ytd

    try:
        data = compute_hr_weekly_report_data(reference_date=ref_date, period=period)
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        return error_response(f'Failed to compute weekly digest: {e}', 500)
