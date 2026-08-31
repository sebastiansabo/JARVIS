from ._shared import *


@events_bp.route('/')
@events_bp.route('/event-bonuses')
@login_required
def event_bonuses():
    """Redirect to React HR page."""
    return redirect('/app/hr')


@events_bp.route('/api/event-bonuses', methods=['GET'])
@login_required
@hr_required
def api_get_event_bonuses():
    """API: Get event bonuses with filters and scope-based access control."""
    year = request.args.get('year', type=int)
    month = request.args.get('month', type=int)
    employee_id = request.args.get('employee_id', type=int)
    event_id = request.args.get('event_id', type=int)

    # Get scope from decorator
    scope = getattr(g, 'permission_scope', 'all')
    user_context = getattr(g, 'user_context', None)

    bonuses = get_all_event_bonuses(
        year=year, month=month,
        employee_id=employee_id, event_id=event_id,
        scope=scope, user_context=user_context
    )

    # Strip monetary values if user cannot view amounts
    is_hr_manager = getattr(current_user, 'is_hr_manager', False)
    role_id = getattr(current_user, 'role_id', None)
    can_view = is_hr_manager
    if not can_view and role_id:
        perm = check_permission_v2(role_id, 'hr', 'bonuses', 'view_amounts')
        can_view = perm.get('has_permission', False)
    if not can_view:
        for b in bonuses:
            b.pop('bonus_net', None)

    return jsonify(bonuses)


@events_bp.route('/api/event-bonuses', methods=['POST'])
@login_required
@hr_permission_required('bonuses', 'add')
def api_create_event_bonus():
    """API: Create a new event bonus."""
    data = request.get_json()

    # Granular presence days (optional): validate against the event range and
    # block if any month they touch is locked; day count drives bonus_days/net.
    try:
        presence_days = resolve_presence_days(data)
        day_hours = resolve_day_hours(data, presence_days)
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    if presence_days:
        user_role = getattr(current_user, 'role_name', 'User')
        ok, reason = check_presence_months_editable(presence_days, user_role)
        if not ok:
            return jsonify({'success': False, 'error': f'Cannot add: {reason}', 'locked': True}), 403
        data['bonus_days'] = len(presence_days)
        if data.get('bonus_type_id'):
            data.pop('bonus_net', None)  # recompute net from the selected day count

    bonus_id = save_event_bonus(
        employee_id=data['employee_id'],
        event_id=data['event_id'],
        year=data['year'],
        month=data['month'],
        participation_start=data.get('participation_start'),
        participation_end=data.get('participation_end'),
        bonus_days=data.get('bonus_days'),
        hours_free=data.get('hours_free'),
        bonus_net=_compute_bonus_net(data),
        details=data.get('details'),
        allocation_month=data.get('allocation_month'),
        created_by=current_user.id,
        presence_days=presence_days,
        day_hours=day_hours,
    )

    # Time Bank auto-credit for hours_free
    _time_bank_credit_hours(data['employee_id'], data.get('hours_free'), bonus_id, data.get('event_id'), current_user.id)

    return jsonify({'success': True, 'id': bonus_id})


@events_bp.route('/api/event-bonuses/bulk', methods=['POST'])
@login_required
@hr_permission_required('bonuses', 'add')
def api_create_event_bonuses_bulk():
    """API: Bulk create event bonuses."""
    data = request.get_json()
    bonuses = data.get('bonuses', [])

    if not bonuses:
        return jsonify({'success': False, 'error': 'No bonuses provided'}), 400

    user_role = getattr(current_user, 'role_name', 'User')
    # Per bonus: resolve/validate presence days, block locked months, then
    # compute bonus_net server-side (day count drives bonus_days).
    for bonus in bonuses:
        try:
            days = resolve_presence_days(bonus)
            bonus['day_hours'] = resolve_day_hours(bonus, days)
        except ValueError as e:
            return jsonify({'success': False, 'error': str(e)}), 400
        if days:
            ok, reason = check_presence_months_editable(days, user_role)
            if not ok:
                return jsonify({'success': False, 'error': f'Cannot add: {reason}', 'locked': True}), 403
            bonus['presence_days'] = days
            bonus['bonus_days'] = len(days)
        bonus['bonus_net'] = _compute_bonus_net(bonus)

    created_ids = save_event_bonuses_bulk(bonuses, created_by=current_user.id)

    # Time Bank auto-credit for hours_free in bulk
    for bonus, bonus_id in zip(bonuses, created_ids):
        _time_bank_credit_hours(bonus['employee_id'], bonus.get('hours_free'), bonus_id, bonus.get('event_id'), current_user.id)

    return jsonify({'success': True, 'ids': created_ids, 'count': len(created_ids)})


@events_bp.route('/api/event-bonuses/<int:bonus_id>', methods=['GET'])
@login_required
@hr_required
def api_get_event_bonus(bonus_id):
    """API: Get a single event bonus."""
    bonus = get_event_bonus(bonus_id)
    if not bonus:
        return error_response('Bonus not found', 404)
    return jsonify(bonus)


@events_bp.route('/api/event-bonuses/<int:bonus_id>', methods=['PUT'])
@login_required
@hr_permission_required('bonuses', 'edit')
def api_update_event_bonus(bonus_id):
    """API: Update an event bonus with scope validation and lock check."""
    # Validate scope access
    scope = getattr(g, 'permission_scope', 'all')
    user_context = getattr(g, 'user_context', None)

    if not can_access_bonus(bonus_id, scope, user_context):
        return jsonify({'success': False, 'error': 'Access denied: bonus outside your scope'}), 403

    # Get existing bonus to check lock status
    bonus = get_event_bonus(bonus_id)
    if not bonus:
        return jsonify({'success': False, 'error': 'Bonus not found'}), 404

    # Check monthly lock (Admin bypasses)
    user_role = getattr(current_user, 'role_name', 'User')
    can_edit, reason = can_edit_bonus(bonus['year'], bonus['month'], user_role)
    if not can_edit:
        return jsonify({
            'success': False,
            'error': f'Cannot edit: {reason}',
            'locked': True
        }), 403

    data = request.get_json()

    # Granular presence days (optional): validate range + block if any month the
    # NEW days touch is locked (the existing month was already checked above).
    try:
        presence_days = resolve_presence_days(data)
        day_hours = resolve_day_hours(data, presence_days)
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    bonus_net = data.get('bonus_net')
    if presence_days:
        ok, reason = check_presence_months_editable(presence_days, user_role)
        if not ok:
            return jsonify({'success': False, 'error': f'Cannot edit: {reason}', 'locked': True}), 403
        data['bonus_days'] = len(presence_days)
        if data.get('bonus_type_id'):
            data.pop('bonus_net', None)  # recompute net from the selected day count
        bonus_net = _compute_bonus_net(data)

    update_event_bonus(
        bonus_id=bonus_id,
        employee_id=data['employee_id'],
        event_id=data['event_id'],
        year=data['year'],
        month=data['month'],
        participation_start=data.get('participation_start'),
        participation_end=data.get('participation_end'),
        bonus_days=data.get('bonus_days'),
        hours_free=data.get('hours_free'),
        bonus_net=bonus_net,
        details=data.get('details'),
        allocation_month=data.get('allocation_month'),
        presence_days=presence_days,
        day_hours=day_hours,
    )

    return jsonify({'success': True})


@events_bp.route('/api/event-bonuses/<int:bonus_id>', methods=['DELETE'])
@login_required
@hr_permission_required('bonuses', 'delete')
def api_delete_event_bonus(bonus_id):
    """API: Delete an event bonus with scope validation and lock check."""
    # Validate scope access
    scope = getattr(g, 'permission_scope', 'all')
    user_context = getattr(g, 'user_context', None)

    if not can_access_bonus(bonus_id, scope, user_context):
        return jsonify({'success': False, 'error': 'Access denied: bonus outside your scope'}), 403

    # Get existing bonus to check lock status
    bonus = get_event_bonus(bonus_id)
    if not bonus:
        return jsonify({'success': False, 'error': 'Bonus not found'}), 404

    # Check monthly lock (Admin bypasses)
    user_role = getattr(current_user, 'role_name', 'User')
    can_edit, reason = can_edit_bonus(bonus['year'], bonus['month'], user_role)
    if not can_edit:
        return jsonify({
            'success': False,
            'error': f'Cannot delete: {reason}',
            'locked': True
        }), 403

    delete_event_bonus(bonus_id)
    return jsonify({'success': True})


@events_bp.route('/api/event-bonuses/bulk-delete', methods=['POST'])
@login_required
@hr_permission_required('bonuses', 'delete')
def api_bulk_delete_event_bonuses():
    """API: Delete multiple event bonuses with scope validation and lock check."""
    data = request.get_json()
    bonus_ids = data.get('ids', [])

    if not bonus_ids:
        return jsonify({'success': False, 'error': 'No IDs provided'}), 400

    # Validate all IDs are integers
    try:
        bonus_ids = [int(id) for id in bonus_ids]
    except (ValueError, TypeError):
        return jsonify({'success': False, 'error': 'Invalid ID format'}), 400

    # Validate scope access for each bonus
    scope = getattr(g, 'permission_scope', 'all')
    user_context = getattr(g, 'user_context', None)

    if scope != 'all':
        for bonus_id in bonus_ids:
            if not can_access_bonus(bonus_id, scope, user_context):
                return jsonify({
                    'success': False,
                    'error': f'Access denied: bonus {bonus_id} outside your scope'
                }), 403

    # Check monthly lock for all bonuses (Admin bypasses)
    user_role = getattr(current_user, 'role_name', 'User')
    if user_role != 'Admin':
        for bonus_id in bonus_ids:
            bonus = get_event_bonus(bonus_id)
            if bonus:
                can_edit, reason = can_edit_bonus(bonus['year'], bonus['month'], user_role)
                if not can_edit:
                    return jsonify({
                        'success': False,
                        'error': f'Cannot delete bonus #{bonus_id}: {reason}',
                        'locked': True
                    }), 403

    deleted_count = delete_event_bonuses_bulk(bonus_ids)
    return jsonify({'success': True, 'deleted': deleted_count})


@events_bp.route('/api/event-bonuses/bulk-delete-by-employee', methods=['POST'])
@login_required
@hr_permission_required('bonuses', 'delete')
def api_bulk_delete_event_bonuses_by_employee():
    """API: Delete all bonuses for given employee IDs with lock check."""
    data = request.get_json()
    employee_ids = data.get('employee_ids', [])

    if not employee_ids:
        return jsonify({'success': False, 'error': 'No employee IDs provided'}), 400

    try:
        employee_ids = [int(id) for id in employee_ids]
    except (ValueError, TypeError):
        return jsonify({'success': False, 'error': 'Invalid ID format'}), 400

    # Check monthly lock - get affected bonuses and verify none are locked (Admin bypasses)
    user_role = getattr(current_user, 'role_name', 'User')
    if user_role != 'Admin':
        # Get bonuses that would be affected
        affected_bonuses = get_bonuses_by_employee(employee_ids)
        for bonus in affected_bonuses:
            can_edit, reason = can_edit_bonus(bonus['year'], bonus['month'], user_role)
            if not can_edit:
                return jsonify({
                    'success': False,
                    'error': f'Cannot delete: some bonuses are locked ({reason})',
                    'locked': True
                }), 403

    deleted_count = delete_event_bonuses_by_employee(employee_ids)
    return jsonify({'success': True, 'deleted': deleted_count})


@events_bp.route('/api/event-bonuses/bulk-delete-by-event', methods=['POST'])
@login_required
@hr_permission_required('bonuses', 'delete')
def api_bulk_delete_event_bonuses_by_event():
    """API: Delete all bonuses for given event/year/month combinations with lock check."""
    data = request.get_json()
    selections = data.get('selections', [])

    if not selections:
        return jsonify({'success': False, 'error': 'No selections provided'}), 400

    # Check monthly lock for each selection (Admin bypasses)
    user_role = getattr(current_user, 'role_name', 'User')
    if user_role != 'Admin':
        for sel in selections:
            year = sel.get('year')
            month = sel.get('month')
            if year and month:
                can_edit, reason = can_edit_bonus(year, month, user_role)
                if not can_edit:
                    return jsonify({
                        'success': False,
                        'error': f'Cannot delete bonuses for {month}/{year}: {reason}',
                        'locked': True
                    }), 403

    deleted_count = delete_event_bonuses_by_event(selections)
    return jsonify({'success': True, 'deleted': deleted_count})


@events_bp.route('/api/lock-status', methods=['GET'])
@login_required
@hr_required
def api_get_lock_status():
    """API: Get lock status for a specific month/year."""
    today = date.today()
    year = request.args.get('year', type=int) or today.year
    month = request.args.get('month', type=int) or today.month

    status = get_lock_status(year, month)
    status['can_override'] = getattr(current_user, 'role_name', 'User') == 'Admin'
    return jsonify(status)


@events_bp.route('/api/hr-settings', methods=['GET'])
@login_required
@hr_required
def api_get_hr_settings():
    """API: Get HR module settings."""
    from core.notifications.repositories import NotificationRepository
    from ..utils import DEFAULT_LOCK_DAY

    settings = NotificationRepository().get_settings()
    lock_day = settings.get('hr_bonus_lock_day')
    max_hours = settings.get('hr_bonus_max_hours_per_day')

    return jsonify({
        'success': True,
        'settings': {
            'hr_bonus_lock_day': int(lock_day) if lock_day else DEFAULT_LOCK_DAY,
            'hr_bonus_max_hours_per_day': int(max_hours) if max_hours else 8
        }
    })


@events_bp.route('/api/hr-settings', methods=['PUT'])
@login_required
@hr_required
def api_update_hr_settings():
    """API: Update HR module settings."""
    # Check permission to edit HR settings
    role_id = getattr(current_user, 'role_id', None)
    if role_id:
        perm = check_permission_v2(role_id, 'hr', 'settings', 'edit')
        if not perm['has_permission']:
            return jsonify({'success': False, 'error': 'Permission denied: hr.settings.edit required'}), 403
    else:
        return jsonify({'success': False, 'error': 'Permission denied'}), 403

    from core.notifications.repositories import NotificationRepository

    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400

    # Update lock day if provided
    if 'hr_bonus_lock_day' in data:
        lock_day = data['hr_bonus_lock_day']
        # Validate: must be between 1 and 28
        if not isinstance(lock_day, int) or lock_day < 1 or lock_day > 28:
            return jsonify({'success': False, 'error': 'Lock day must be between 1 and 28'}), 400
        NotificationRepository().save_setting('hr_bonus_lock_day', str(lock_day))

    # Update max hours per day if provided
    if 'hr_bonus_max_hours_per_day' in data:
        max_hours = data['hr_bonus_max_hours_per_day']
        if not isinstance(max_hours, int) or max_hours < 1 or max_hours > 24:
            return jsonify({'success': False, 'error': 'Max hours per day must be between 1 and 24'}), 400
        NotificationRepository().save_setting('hr_bonus_max_hours_per_day', str(max_hours))

    return jsonify({'success': True})


def _time_bank_credit_hours(employee_id, hours_free, bonus_id, event_id, created_by):
    """Auto-credit Time Bank when a bonus with hours_free is created."""
    if not hours_free or int(hours_free) <= 0:
        return
    try:
        from hr.time_bank.service import TimeBankService
        svc = TimeBankService()
        event_name = ''
        if event_id:
            ev = get_hr_event(event_id)
            event_name = ev.get('name', '') if ev else ''
        svc.credit(
            user_id=int(employee_id),
            amount=int(hours_free),
            tx_type='marketing_event',
            description=f'Marketing event: {event_name}' if event_name else 'Marketing event bonus',
            reference_type='bonus',
            reference_id=bonus_id,
            created_by=created_by,
        )
    except Exception:
        import logging
        logging.getLogger('jarvis.hr.time_bank').exception(
            'Failed to credit Time Bank for bonus %s', bonus_id,
        )
