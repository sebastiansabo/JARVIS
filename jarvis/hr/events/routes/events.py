from ._shared import *


@events_bp.route('/events')
@login_required
def events():
    """Redirect to React HR page."""
    return redirect('/app/hr')


@events_bp.route('/events/new')
@login_required
def add_event():
    """Redirect to React HR add event page."""
    return redirect('/app/hr/add-event')


@events_bp.route('/api/events', methods=['GET'])
@login_required
@v2_permission_required('hr', 'events', 'view')
def api_get_events():
    """API: Get all events. Requires hr.events.view permission."""
    from datetime import date
    limit = request.args.get('limit', 200, type=int)
    offset = request.args.get('offset', 0, type=int)
    events = get_all_hr_events(limit=limit, offset=offset)
    upcoming_param = request.args.get('upcoming')
    if upcoming_param is not None:
        today = date.today().isoformat()
        if upcoming_param.lower() == 'true':
            events = [e for e in events if (e.get('start_date') or '') >= today]
        else:
            events = [e for e in events if (e.get('end_date') or e.get('start_date') or '') < today]
    # Map field names for mobile compatibility
    for e in events:
        if 'name' in e and 'title' not in e:
            e['title'] = e['name']
        if 'start_date' in e and 'date' not in e:
            e['date'] = e['start_date']
        e.setdefault('status', 'active')
        e.setdefault('location', e.get('company') or '')
        e.setdefault('participants_count', 0)
        e.setdefault('type', 'HR Event')
    # Wrap in {events: [...]} when upcoming param used (mobile), bare array otherwise (web)
    if upcoming_param is not None:
        return jsonify({'events': events})
    return jsonify(events)


@events_bp.route('/api/events', methods=['POST'])
@login_required
@hr_permission_required('events', 'add')
def api_create_event():
    """API: Create a new event."""
    data = request.get_json()

    event_id = save_hr_event(
        name=data['name'],
        start_date=data['start_date'],
        end_date=data['end_date'],
        company=data.get('company'),
        brand=data.get('brand'),
        description=data.get('description'),
        created_by=current_user.id
    )

    # Auto-tag rules (fire-and-forget)
    try:
        from core.tags.auto_tag_service import AutoTagService
        AutoTagService().evaluate_rules_for_entity('event', event_id, current_user.id)
    except Exception:
        pass

    return jsonify({'success': True, 'id': event_id})


@events_bp.route('/api/events/<int:event_id>', methods=['GET'])
@login_required
@hr_required
def api_get_event(event_id):
    """API: Get a single event."""
    event = get_hr_event(event_id)
    if not event:
        return error_response('Event not found', 404)
    return jsonify(event)


@events_bp.route('/api/events/<int:event_id>', methods=['PUT'])
@login_required
@hr_permission_required('events', 'edit')
def api_update_event(event_id):
    """API: Update an event."""
    data = request.get_json()

    update_hr_event(
        event_id=event_id,
        name=data['name'],
        start_date=data['start_date'],
        end_date=data['end_date'],
        company=data.get('company'),
        brand=data.get('brand'),
        description=data.get('description')
    )

    return jsonify({'success': True})


@events_bp.route('/api/events/<int:event_id>', methods=['DELETE'])
@login_required
@hr_permission_required('events', 'delete')
def api_delete_event(event_id):
    """API: Delete an event."""
    delete_hr_event(event_id)
    return jsonify({'success': True})


@events_bp.route('/api/events/bulk-delete', methods=['POST'])
@login_required
@hr_permission_required('events', 'delete')
def api_bulk_delete_events():
    """API: Delete multiple events."""
    data = request.get_json()
    event_ids = data.get('ids', [])

    if not event_ids:
        return jsonify({'success': False, 'error': 'No IDs provided'}), 400

    try:
        event_ids = [int(id) for id in event_ids]
    except (ValueError, TypeError):
        return jsonify({'success': False, 'error': 'Invalid ID format'}), 400

    deleted_count = delete_hr_events_bulk(event_ids)
    return jsonify({'success': True, 'deleted': deleted_count})
