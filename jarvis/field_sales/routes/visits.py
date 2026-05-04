"""Field Sales visit routes — today, create, detail, checkin, checkout, note, brief."""

from ._shared import *  # noqa: F401, F403


@field_sales_bp.route('/api/field-sales/visits/today', methods=['GET'])
@jwt_or_login_required
@field_sales_required
def api_visits_today():
    """Get visits for the current KAM for a given date (default: today)."""
    try:
        date_str = request.args.get('date')
        if date_str:
            try:
                datetime.strptime(date_str, '%Y-%m-%d')
            except ValueError:
                return jsonify({'success': False, 'error': 'Invalid date format. Use YYYY-MM-DD'}), 400
        else:
            date_str = date.today().isoformat()

        visits = _visit_repo.get_by_kam_and_date(_get_current_user().id, date_str)
        return jsonify({'success': True, 'visits': visits, 'date': date_str})
    except Exception as e:
        logger.exception('Error fetching visits for today')
        return jsonify({'success': False, 'error': _safe_error(e)}), 500


@field_sales_bp.route('/api/field-sales/visits', methods=['POST'])
@jwt_or_login_required
@field_sales_required
def api_create_visit():
    """Create a new visit plan."""
    try:
        data = request.get_json(silent=True) or {}

        client_id = data.get('client_id')
        planned_date = data.get('planned_date')

        if not client_id:
            return jsonify({'success': False, 'error': 'client_id is required'}), 400
        if not planned_date:
            return jsonify({'success': False, 'error': 'planned_date is required'}), 400

        try:
            client_id = int(client_id)
        except (ValueError, TypeError):
            return jsonify({'success': False, 'error': 'client_id must be an integer'}), 400

        try:
            datetime.strptime(planned_date, '%Y-%m-%d')
        except ValueError:
            return jsonify({'success': False, 'error': 'Invalid date format. Use YYYY-MM-DD'}), 400

        visit_type = data.get('visit_type', 'general')
        if visit_type not in ALLOWED_VISIT_TYPES:
            return jsonify({'success': False, 'error': f'Invalid visit_type. Allowed: {", ".join(sorted(ALLOWED_VISIT_TYPES))}'}), 400

        # Verify client exists
        client = _client_repo.get_by_id(client_id)
        if not client:
            return jsonify({'success': False, 'error': 'Client not found'}), 404

        # Determine KAM: manager can assign to another user
        kam_id_param = data.get('kam_id')
        current_uid = _get_current_user().id
        if kam_id_param and int(kam_id_param) != current_uid:
            if not _is_manager():
                return jsonify({'success': False, 'error': 'Only managers can assign visits to other KAMs'}), 403
            from core.auth.repositories import UserRepository
            target = UserRepository().get_by_id(int(kam_id_param))
            if not target or not target.get('is_active', True):
                return jsonify({'success': False, 'error': 'Target KAM not found or inactive'}), 404
            kam_id = int(kam_id_param)
        else:
            kam_id = current_uid

        visit_data = {
            'kam_id': kam_id,
            'client_id': client_id,
            'planned_date': planned_date,
            'planned_time': data.get('planned_time'),
            'visit_type': visit_type,
            'goals': data.get('goals'),
        }

        visit = _visit_repo.create(visit_data)
        visit_id = visit['id']

        # Fetch client name for notifications
        client = _client_repo.get_by_id(client_id)
        client_display = client.get('display_name', 'Client') if client else 'Client'
        visit['client_name'] = client_display

        # Generate AI brief in background with proper app context
        app = current_app._get_current_object()
        kam_name = getattr(current_user, 'name', None) or 'KAM'

        def _generate_brief():
            context = _visit_repo.get_client_context(visit_id)
            if context:
                brief = ai_service.generate_visit_brief(context)
                if brief:
                    _visit_repo.update_brief(visit_id, brief)

        _run_background(app, _generate_brief)

        # Notify manager about planned visit (fire-and-forget in background)
        _visit_notification = dict(visit)
        _visit_notification['kam_id'] = kam_id

        def _send_planned_notification():
            notify_visit_planned(_visit_notification, kam_name=kam_name)

        _run_background(app, _send_planned_notification)

        # If manager assigned to another KAM, notify that KAM via push
        if kam_id != current_uid:
            assigner_name = kam_name

            def _send_assigned_notification():
                from core.notifications.notify import notify_user
                notify_user(
                    kam_id,
                    f'Vizita asignata — {client_display}',
                    message=f'{assigner_name} ti-a asignat o vizita la {client_display} pe {planned_date}',
                    link='/app/sales/field-sales',
                    entity_type='field_sales_visit',
                    entity_id=visit_id,
                    type='info',
                    category='field_sales',
                )

            _run_background(app, _send_assigned_notification)

        return jsonify({'success': True, 'visit': visit}), 201
    except Exception as e:
        logger.exception('Error creating visit')
        return jsonify({'success': False, 'error': _safe_error(e)}), 500


@field_sales_bp.route('/api/field-sales/routes', methods=['POST'])
@jwt_or_login_required
@field_sales_manager_required
def api_create_route():
    """Create a visit route with multiple stops for a KAM."""
    try:
        data = request.get_json(silent=True) or {}

        kam_id = data.get('kam_id')
        planned_date = data.get('planned_date')
        stops = data.get('stops', [])

        if not kam_id:
            return jsonify({'success': False, 'error': 'kam_id is required'}), 400
        if not planned_date:
            return jsonify({'success': False, 'error': 'planned_date is required'}), 400
        if not stops or not isinstance(stops, list):
            return jsonify({'success': False, 'error': 'At least one stop is required'}), 400

        try:
            kam_id = int(kam_id)
        except (ValueError, TypeError):
            return jsonify({'success': False, 'error': 'kam_id must be an integer'}), 400

        try:
            datetime.strptime(planned_date, '%Y-%m-%d')
        except ValueError:
            return jsonify({'success': False, 'error': 'Invalid date format. Use YYYY-MM-DD'}), 400

        # Verify KAM exists and is active
        from core.auth.repositories import UserRepository
        target = UserRepository().get_by_id(kam_id)
        if not target or not target.get('is_active', True):
            return jsonify({'success': False, 'error': 'KAM not found or inactive'}), 404

        # Validate stops
        for i, stop in enumerate(stops):
            if not stop.get('client_id'):
                return jsonify({'success': False, 'error': f'Stop {i+1}: client_id is required'}), 400
            vt = stop.get('visit_type', 'general')
            if vt not in ALLOWED_VISIT_TYPES:
                return jsonify({'success': False, 'error': f'Stop {i+1}: invalid visit_type'}), 400

        current_uid = _get_current_user().id
        route_data = {
            'kam_id': kam_id,
            'planned_date': planned_date,
            'name': data.get('name'),
            'created_by': current_uid,
            'stops': stops,
        }

        route = _visit_repo.create_route(route_data)

        # Generate AI briefs in background for each visit
        app = current_app._get_current_object()
        visit_ids = [v['id'] for v in route.get('visits', [])]

        def _generate_briefs():
            for vid in visit_ids:
                try:
                    context = _visit_repo.get_client_context(vid)
                    if context:
                        brief = ai_service.generate_visit_brief(context)
                        if brief:
                            _visit_repo.update_brief(vid, brief)
                except Exception:
                    logger.exception('Brief generation failed for visit %s', vid)

        _run_background(app, _generate_briefs)

        # Notify KAM about assigned route
        stop_count = len(stops)
        kam_name = getattr(current_user, 'name', None) or 'Manager'
        route_name = data.get('name') or f'Ruta {planned_date}'

        def _send_route_notification():
            from core.notifications.notify import notify_user
            notify_user(
                kam_id,
                f'Ruta asignata — {stop_count} vizite pe {planned_date}',
                message=f'{kam_name} ti-a asignat ruta "{route_name}" cu {stop_count} opriri pe {planned_date}',
                link='/app/sales/field-sales',
                entity_type='field_sales_route',
                entity_id=route['id'],
                type='info',
                category='field_sales',
            )

        _run_background(app, _send_route_notification)

        return jsonify({'success': True, 'route': route}), 201
    except Exception as e:
        logger.exception('Error creating route')
        return jsonify({'success': False, 'error': _safe_error(e)}), 500


@field_sales_bp.route('/api/field-sales/routes', methods=['GET'])
@jwt_or_login_required
@field_sales_manager_required
def api_list_routes():
    """List routes in a date range."""
    try:
        date_from = request.args.get('date_from')
        date_to = request.args.get('date_to')
        if not date_from or not date_to:
            return jsonify({'success': False, 'error': 'date_from and date_to are required'}), 400
        kam_id = request.args.get('kam_id', type=int)
        routes = _visit_repo.get_routes(date_from, date_to, kam_id=kam_id)
        return jsonify({'success': True, 'routes': routes})
    except Exception as e:
        logger.exception('Error listing routes')
        return jsonify({'success': False, 'error': _safe_error(e)}), 500


@field_sales_bp.route('/api/field-sales/visits/<int:visit_id>', methods=['GET'])
@jwt_or_login_required
@field_sales_required
def api_visit_detail(visit_id):
    """Get full visit details including notes."""
    try:
        visit = _visit_repo.get_by_id(visit_id)
        if not visit:
            return jsonify({'success': False, 'error': 'Visit not found'}), 404

        # IDOR check: KAM sees own visits, managers see all
        if visit['kam_id'] != _get_current_user().id and not _is_manager():
            return jsonify({'success': False, 'error': 'Access denied'}), 403

        return jsonify({'success': True, 'visit': visit})
    except Exception as e:
        logger.exception('Error fetching visit detail')
        return jsonify({'success': False, 'error': _safe_error(e)}), 500


@field_sales_bp.route('/api/field-sales/visits/<int:visit_id>', methods=['PUT'])
@jwt_or_login_required
@field_sales_manager_required
def api_update_visit(visit_id):
    """Manager/admin: update visit fields (date, time, type, goals, status, outcome)."""
    try:
        visit = _visit_repo.get_by_id(visit_id)
        if not visit:
            return jsonify({'success': False, 'error': 'Visit not found'}), 404

        data = request.get_json(silent=True) or {}
        update = {}

        if 'planned_date' in data:
            try:
                datetime.strptime(data['planned_date'], '%Y-%m-%d')
                update['planned_date'] = data['planned_date']
            except ValueError:
                return jsonify({'success': False, 'error': 'Invalid date format'}), 400

        if 'planned_time' in data:
            update['planned_time'] = data['planned_time'] or None

        if 'visit_type' in data:
            if data['visit_type'] not in ALLOWED_VISIT_TYPES:
                return jsonify({'success': False, 'error': 'Invalid visit_type'}), 400
            update['visit_type'] = data['visit_type']

        if 'goals' in data:
            update['goals'] = data['goals']

        if 'contact_person' in data:
            update['contact_person'] = data['contact_person'] or None

        if 'companions' in data:
            companions = data['companions']
            if not isinstance(companions, list):
                return jsonify({'success': False, 'error': 'companions must be an array'}), 400
            update['companions'] = companions

        if 'pre_visit_data' in data:
            if not isinstance(data['pre_visit_data'], dict):
                return jsonify({'success': False, 'error': 'pre_visit_data must be an object'}), 400
            update['pre_visit_data'] = data['pre_visit_data']

        if 'post_visit_data' in data:
            if not isinstance(data['post_visit_data'], dict):
                return jsonify({'success': False, 'error': 'post_visit_data must be an object'}), 400
            update['post_visit_data'] = data['post_visit_data']

        if 'status' in data:
            allowed_statuses = {'planned', 'in_progress', 'completed', 'no_show', 'rescheduled', 'partial'}
            if data['status'] not in allowed_statuses:
                return jsonify({'success': False, 'error': 'Invalid status'}), 400
            update['status'] = data['status']

        if 'outcome' in data:
            if data['outcome'] and data['outcome'] not in ALLOWED_OUTCOMES:
                return jsonify({'success': False, 'error': 'Invalid outcome'}), 400
            update['outcome'] = data['outcome'] or None

        if not update:
            return jsonify({'success': False, 'error': 'No fields to update'}), 400

        updated = _visit_repo.update_visit(visit_id, update)
        return jsonify({'success': True, 'visit': updated})
    except Exception as e:
        logger.exception('Error updating visit')
        return jsonify({'success': False, 'error': _safe_error(e)}), 500


@field_sales_bp.route('/api/field-sales/visits/<int:visit_id>/checkin', methods=['PUT', 'POST'])
@jwt_or_login_required
@field_sales_required
def api_visit_checkin(visit_id):
    """Check in to a visit with optional GPS coordinates."""
    try:
        visit = _visit_repo.get_by_id(visit_id)
        if not visit:
            return jsonify({'success': False, 'error': 'Visit not found'}), 404

        # IDOR: only own visits
        if visit['kam_id'] != _get_current_user().id:
            return jsonify({'success': False, 'error': 'Can only check in to your own visits'}), 403

        if visit['status'] not in ('planned', 'in_progress'):
            return jsonify({'success': False, 'error': f'Cannot check in to a {visit["status"]} visit'}), 400

        data = request.get_json(silent=True) or {}
        lat = data.get('lat')
        lng = data.get('lng')

        # Validate GPS coordinates if provided
        if lat is not None:
            try:
                lat = float(lat)
                if not (-90 <= lat <= 90):
                    return jsonify({'success': False, 'error': 'lat must be between -90 and 90'}), 400
            except (ValueError, TypeError):
                return jsonify({'success': False, 'error': 'lat must be a number'}), 400
        if lng is not None:
            try:
                lng = float(lng)
                if not (-180 <= lng <= 180):
                    return jsonify({'success': False, 'error': 'lng must be between -180 and 180'}), 400
            except (ValueError, TypeError):
                return jsonify({'success': False, 'error': 'lng must be a number'}), 400

        updated = _visit_repo.checkin(visit_id, lat=lat, lng=lng)
        return jsonify({'success': True, 'visit': updated})
    except Exception as e:
        logger.exception('Error checking in to visit')
        return jsonify({'success': False, 'error': _safe_error(e)}), 500


@field_sales_bp.route('/api/field-sales/visits/<int:visit_id>/checkout', methods=['POST'])
@jwt_or_login_required
@field_sales_required
def api_visit_checkout(visit_id):
    """Check out from a visit (complete without note)."""
    try:
        visit = _visit_repo.get_by_id(visit_id)
        if not visit:
            return jsonify({'success': False, 'error': 'Visit not found'}), 404

        if visit['kam_id'] != _get_current_user().id:
            return jsonify({'success': False, 'error': 'Can only check out from your own visits'}), 403

        if visit['status'] != 'in_progress':
            return jsonify({'success': False, 'error': 'Can only check out from in_progress visits'}), 400

        data = request.get_json(silent=True) or {}
        outcome = data.get('outcome', 'completed')
        if outcome not in ALLOWED_OUTCOMES:
            return jsonify({'success': False, 'error': f'Invalid outcome. Allowed: {", ".join(sorted(ALLOWED_OUTCOMES))}'}), 400

        updated = _visit_repo.complete(visit_id, outcome)
        return jsonify({'success': True, 'visit': updated})
    except Exception as e:
        logger.exception('Error checking out from visit')
        return jsonify({'success': False, 'error': _safe_error(e)}), 500


@field_sales_bp.route('/api/field-sales/visits/<int:visit_id>/note', methods=['POST'])
@jwt_or_login_required
@field_sales_required
def api_visit_note(visit_id):
    """Submit a visit note. Structures via AI and completes the visit."""
    try:
        visit = _visit_repo.get_by_id(visit_id)
        if not visit:
            return jsonify({'success': False, 'error': 'Visit not found'}), 404

        # IDOR: only own visits
        if visit['kam_id'] != _get_current_user().id:
            return jsonify({'success': False, 'error': 'Can only add notes to your own visits'}), 403

        data = request.get_json(silent=True) or {}
        raw_note = data.get('raw_note', '').strip()
        outcome = data.get('outcome', 'completed')

        if not raw_note:
            return jsonify({'success': False, 'error': 'raw_note is required'}), 400
        if len(raw_note) > 10000:
            return jsonify({'success': False, 'error': 'raw_note must be under 10000 characters'}), 400
        if outcome not in ALLOWED_OUTCOMES:
            return jsonify({'success': False, 'error': f'Invalid outcome. Allowed: {", ".join(sorted(ALLOWED_OUTCOMES))}'}), 400

        # 1. Save raw note first
        note = _visit_repo.add_note(visit_id, raw_note)

        # 2. Structure via AI (synchronous — user waits)
        structured = None
        try:
            client_context = _visit_repo.get_client_context(visit_id)
            structured = ai_service.structure_visit_note(raw_note, client_context)
        except Exception:
            logger.exception('AI structuring failed for visit %s', visit_id)

        # 3. Save structured note
        if structured and not structured.get('error'):
            _visit_repo.update_note_structured(note['id'], structured)
            note['structured_note'] = structured
            note['structured_at'] = datetime.now().isoformat()

        # 4. Complete visit
        _visit_repo.complete(visit_id, outcome)

        # 5. Background: recompute renewal score + send notifications
        client_id = visit['client_id']
        client_name = visit.get('client_name', 'Client')
        app = current_app._get_current_object()
        kam_name = getattr(current_user, 'name', None) or 'KAM'
        _visit_copy = dict(visit)
        _structured_copy = dict(structured) if structured else None

        def _post_note_tasks():
            # Recompute renewal score and trigger threshold notification
            profile = _client_repo.get_or_create_profile(client_id)
            previous_score = profile.get('renewal_score') or 0
            new_score = segmentation_service.compute_renewal_score(client_id, _client_repo)
            _client_repo.update_renewal_score(client_id, new_score)

            assigned_kam_id = profile.get('assigned_kam_id') or _visit_copy.get('kam_id')
            notify_high_renewal_score(
                client_id, client_name, new_score, previous_score,
                assigned_kam_id=assigned_kam_id,
            )

            # High value opportunity notification
            notify_high_value_opportunity(_visit_copy, _structured_copy, kam_name=kam_name)

            # Risk flags notification
            notify_risk_flags(_visit_copy, _structured_copy, kam_name=kam_name)

        _run_background(app, _post_note_tasks)

        return jsonify({
            'success': True,
            'note': note,
            'structured_note': structured,
            'visit_status': 'completed',
        })
    except Exception as e:
        logger.exception('Error submitting visit note')
        return jsonify({'success': False, 'error': _safe_error(e)}), 500


@field_sales_bp.route('/api/field-sales/visits/<int:visit_id>/brief', methods=['GET'])
@jwt_or_login_required
@field_sales_required
def api_visit_brief(visit_id):
    """Get or regenerate the AI brief for a visit."""
    try:
        visit = _visit_repo.get_by_id(visit_id)
        if not visit:
            return jsonify({'success': False, 'error': 'Visit not found'}), 404

        # IDOR: own visits or manager
        if visit['kam_id'] != _get_current_user().id and not _is_manager():
            return jsonify({'success': False, 'error': 'Access denied'}), 403

        refresh = request.args.get('refresh', '').lower() in ('1', 'true')

        if visit.get('ai_brief') and not refresh:
            return jsonify({
                'success': True,
                'brief': visit['ai_brief'],
                'generated_at': visit.get('ai_brief_generated_at'),
            })

        # Generate fresh brief
        context = _visit_repo.get_client_context(visit_id)
        if not context:
            return jsonify({'success': False, 'error': 'Could not build client context'}), 500

        brief = ai_service.generate_visit_brief(context)
        if brief:
            _visit_repo.update_brief(visit_id, brief)

        return jsonify({
            'success': True,
            'brief': brief or '',
            'generated_at': datetime.now().isoformat() if brief else None,
        })
    except Exception as e:
        logger.exception('Error generating visit brief')
        return jsonify({'success': False, 'error': _safe_error(e)}), 500
