from ._shared import *


class _LazyFSRepo:
    """Lazy proxy — defers field_sales import until first use."""
    _inst = None

    def _get(self):
        if self.__class__._inst is None:
            from field_sales.repositories.client_fs_repository import ClientFSRepository
            self.__class__._inst = ClientFSRepository()
        return self.__class__._inst

    def __getattr__(self, name):
        return getattr(self._get(), name)

_fs_repo = _LazyFSRepo()


_GATE_FIELDS = ('full_name', 'email', 'phone', 'driver_license_photo',
                'driver_license_serie', 'driver_license_number')


def contact_gate_valid(contact):
    """A company contact is gate-valid when it carries all personal + license details."""
    return bool(contact) and all(contact.get(f) for f in _GATE_FIELDS)


# ════════════════════════════════════════════════════════════════
# Clients
# ════════════════════════════════════════════════════════════════

def _scope_company_ids():
    """Company IDs the current user may see per g.permission_scope, or None for 'all'.

    None  -> no filtering (scope 'all').
    [id]  -> department/own: restrict to the user's own company. 'own' collapses
             to department for now because per-KAM client ownership
             (client_profiles.assigned_kam_id) is not yet populated.
    []    -> a scoped user with no company_id: sees nothing (fail closed).
    """
    scope = getattr(g, 'permission_scope', 'all')
    if scope == 'all':
        return None
    uc = getattr(current_user, 'company_id', None)
    return [uc] if uc is not None else []


@crm_bp.route('/api/crm/clients', methods=['GET'])
@login_required
@crm_required
def api_clients():
    rows, total = _client_repo.search(
        company_ids=_scope_company_ids(),
        q=request.args.get('q'),
        name=request.args.get('name'),
        phone=request.args.get('phone'),
        email=request.args.get('email'),
        client_type=request.args.get('client_type'),
        responsible=request.args.get('responsible'),
        city=request.args.get('city'),
        date_from=request.args.get('date_from'),
        date_to=request.args.get('date_to'),
        sort_by=request.args.get('sort_by'),
        sort_order=request.args.get('sort_order'),
        show_blacklisted=request.args.get('show_blacklisted'),
        limit=request.args.get('limit', 50, type=int),
        offset=request.args.get('offset', 0, type=int),
    )
    return jsonify({'clients': rows, 'total': total})


@crm_bp.route('/api/crm/clients/export', methods=['GET'])
@login_required
@crm_required
def api_clients_export():
    if not getattr(current_user, 'can_export_crm', False):
        return jsonify({'success': False, 'error': 'Export permission denied'}), 403
    rows, _ = _client_repo.search(
        company_ids=_scope_company_ids(),
        name=request.args.get('name'), phone=request.args.get('phone'),
        email=request.args.get('email'), client_type=request.args.get('client_type'),
        responsible=request.args.get('responsible'), city=request.args.get('city'),
        date_from=request.args.get('date_from'), date_to=request.args.get('date_to'),
        show_blacklisted=request.args.get('show_blacklisted'),
        limit=50000, offset=0,
    )
    return _csv_response(rows, 'clients.csv', [
        'id', 'display_name', 'client_type', 'phone', 'email', 'street', 'city',
        'region', 'company_name', 'responsible', 'created_at',
    ])


@crm_bp.route('/api/crm/clients/<int:client_id>', methods=['GET'])
@login_required
@crm_required
def api_client_detail(client_id):
    """360 Client — full ecosystem data for a single client."""
    from field_sales.services.business_data_service import get_connected_business_connectors
    _ensure_enrichment_column()
    client = _client_repo.get_by_id(client_id)
    if not client:
        return jsonify({'success': False, 'error': 'Not found'}), 404

    # Per-client tenant scope is enforced centrally by @crm_required.

    # Auto-fix: parse nr_reg from name, detect company type
    client = _auto_fix_client_on_load(client_id, client)

    deals, _ = _deal_repo.search(client_id=client_id, limit=200)

    # Fallback: if 0 deals by client_id, find deals with an EXACT-name match and
    # attribute only genuinely-orphaned ones (client_id IS NULL). Never a
    # substring match, never a reassignment of another client's deals.
    if not deals:
        display_name = client.get('display_name') or ''
        if display_name:
            # Match on the clean name (nr_reg stripped), exact/normalized
            clean_name, _ = _parse_name_nr_reg(display_name)
            fallback = _deal_repo.search_by_buyer_name(clean_name, limit=200)
            if fallback:
                logger.info('Found %d exact-name deals for "%s", attributing orphans to client %s',
                            len(fallback), clean_name, client_id)
                try:
                    _deal_repo.relink_to_client(clean_name, client_id)
                except Exception:
                    logger.exception('Failed to relink deals for client %s', client_id)
                deals = fallback

    phones = []
    try:
        phones = _client_repo.get_phones(client_id)
    except Exception:
        pass  # client_phones table may not exist yet

    # Full 360 ecosystem data
    view_360 = {}
    try:
        view_360 = _fs_repo.get_360(client_id)
    except Exception:
        logger.exception('Error fetching 360 view for client %s', client_id)

    profile = view_360.get('profile')
    fleet = view_360.get('fleet') or []
    visits = view_360.get('visit_history') or []
    interactions = view_360.get('interactions') or []
    renewal_candidates = view_360.get('renewal_candidates') or []
    fiscal = view_360.get('fiscal')

    # Auto-compute fleet_size from deals if no fleet vehicles
    if profile and not fleet and deals:
        current_fleet_size = profile.get('fleet_size') or 0
        if current_fleet_size == 0:
            try:
                _fs_repo.update_profile(client_id, {'fleet_size': len(deals)})
                profile = _fs_repo.get_or_create_profile(client_id)
            except Exception:
                pass

    # Parse enrichment_data from profile
    enrichment_data = {}
    if profile:
        ed = profile.get('enrichment_data')
        if isinstance(ed, str):
            try:
                import json as _json
                enrichment_data = _json.loads(ed)
            except (ValueError, TypeError):
                pass
        elif isinstance(ed, dict):
            enrichment_data = ed

    # Get available connectors for this client
    connectors = get_connected_business_connectors()

    # ── Compute Business Value Score ──
    bv = _compute_business_value(client, profile, deals, fleet, visits, interactions)

    return jsonify({
        'client': client,
        'deals': deals,
        'phones': phones,
        'profile': profile,
        'fleet': fleet,
        'visits': visits,
        'interactions': interactions,
        'renewal_candidates': renewal_candidates,
        'fiscal': fiscal,
        'enrichment_data': enrichment_data,
        'connectors': connectors,
        'business_value': bv,
    })


@crm_bp.route('/api/crm/clients/<int:client_id>', methods=['PUT'])
@login_required
@crm_required
def api_client_update(client_id):
    if not getattr(current_user, 'can_edit_crm', False):
        return jsonify({'success': False, 'error': 'Edit permission denied'}), 403
    data = request.get_json(silent=True) or {}
    result = _client_repo.update(client_id, data)
    if not result:
        return jsonify({'success': False, 'error': 'Not found or no editable fields'}), 404
    return jsonify({'success': True, 'client': result})


@crm_bp.route('/api/crm/clients/<int:client_id>/enrich', methods=['POST'])
@login_required
@crm_required
def api_client_enrich(client_id):
    """Enrich client with ANAF fiscal data by CUI."""
    from field_sales.services.segmentation_service import get_or_refresh_anaf
    from field_sales.services.business_data_service import search_company_by_name
    client = _client_repo.get_by_id(client_id)
    if not client:
        return jsonify({'success': False, 'error': 'Not found'}), 404

    data = request.get_json(silent=True) or {}
    cui = data.get('cui', '').strip()

    # Ensure profile exists
    try:
        profile = _fs_repo.get_or_create_profile(client_id)
        if cui:
            _fs_repo.update_profile(client_id, {'cui': cui})
        elif profile.get('cui'):
            cui = str(profile['cui']).strip()
    except Exception:
        logger.exception('Error setting CUI for client %s', client_id)

    # Enrichment chain: connectors by name → ANAF by CUI → AI fallback
    try:
        import json
        from datetime import datetime as _dt

        anaf_data = None
        source = 'anaf'
        cui_correction = None
        company_name = client.get('display_name') or client.get('company_name') or ''
        # Also try nr_reg as search hint
        nr_reg = client.get('nr_reg') or ''

        # Clean name (strip nr_reg if embedded)
        clean_name, parsed_nr_reg = _parse_name_nr_reg(company_name)
        if parsed_nr_reg and not nr_reg:
            nr_reg = parsed_nr_reg
        search_name = clean_name or company_name

        # Step 0: Local DB lookup — check if we already have a CUI for a similar company
        if not cui and search_name:
            local_match = _client_repo.find_by_normalized_name(search_name.lower())
            if local_match and local_match.get('cui'):
                cui = str(local_match['cui']).strip()
                logger.info('Local DB found CUI %s for "%s" (matched: %s)',
                            cui, search_name, local_match.get('display_name'))
                _fs_repo.update_profile(client_id, {'cui': cui})

        # Step 1: Search connectors by company name to find/verify CUI
        if search_name:
            matches = search_company_by_name(search_name)
            if not matches and nr_reg:
                # Fallback: search by Nr. Reg. Com.
                matches = search_company_by_name(nr_reg)
            if matches:
                best = matches[0]
                found_cui = str(best.get('cui', '')).strip()
                if found_cui and found_cui != cui:
                    cui_correction = {
                        'old_cui': cui or '(none)',
                        'new_cui': found_cui,
                        'found_name': best.get('name', ''),
                        'source': best.get('source', ''),
                    }
                    logger.info('CUI correction for %s: saved=%s, found=%s from %s',
                                search_name, cui, found_cui, best.get('source'))
                    cui = found_cui
                    _fs_repo.update_profile(client_id, {'cui': cui})
                elif found_cui and not cui:
                    cui = found_cui
                    _fs_repo.update_profile(client_id, {'cui': cui})
                # Also store nr_reg if found
                found_nr_reg = best.get('nr_reg', '')
                if found_nr_reg and not nr_reg:
                    _client_repo.update(client_id, {'nr_reg': found_nr_reg})

        # Step 2: Fetch ANAF with (potentially found/corrected) CUI
        if cui:
            anaf_data = get_or_refresh_anaf(client_id, cui, _fs_repo)

        # Step 3: AI fallback if still nothing. This is an UNVERIFIED GUESS and
        # must never be written to anaf_data or applied to the profile as fiscal
        # truth — that let a hallucinated company overwrite real fiscal fields.
        ai_guess = None
        if not anaf_data:
            logger.info('ANAF empty for %s (CUI %s), trying AI fallback', search_name, cui)
            ai_guess = _ai_company_lookup(search_name, cui)
            source = 'ai'

        # Persist VERIFIED ANAF data to the fiscal fields; quarantine AI guesses.
        if anaf_data and isinstance(anaf_data, dict):
            _apply_connector_to_profile(client_id, 'anaf', anaf_data)
            _fs_repo.update_profile(client_id, {
                'anaf_data': json.dumps(anaf_data),
                'anaf_fetched_at': _dt.now().isoformat(),
            })
        elif ai_guess and isinstance(ai_guess, dict):
            # Store under enrichment_data.ai_guess with a review flag — NEVER in
            # anaf_data. Do not auto-set the profile CUI from a guess either: a
            # wrong CUI would poison every future ANAF fetch.
            try:
                _ensure_enrichment_column()
                profile_obj = _fs_repo.get_or_create_profile(client_id)
                existing = profile_obj.get('enrichment_data') or {}
                if isinstance(existing, str):
                    existing = json.loads(existing) if existing else {}
                existing['ai_guess'] = {
                    'data': ai_guess,
                    'unverified': True,
                    'needs_review': True,
                    'fetched_at': _dt.now().isoformat(),
                }
                _fs_repo.update_profile(client_id, {'enrichment_data': json.dumps(existing)})
            except Exception:
                logger.exception('Failed to store AI guess for client %s', client_id)

        profile = _fs_repo.get_or_create_profile(client_id)
        resp = {
            'success': True,
            'profile': profile,
            'fiscal': anaf_data or ai_guess,
            'source': source,
            'unverified': bool(ai_guess and not anaf_data),
        }
        if cui_correction:
            resp['cui_correction'] = cui_correction
        return jsonify(resp)
    except Exception:
        logger.exception('ANAF enrichment failed for client %s', client_id)
        return jsonify({'success': False, 'error': 'Enrichment failed'}), 500


@crm_bp.route('/api/crm/clients/<int:client_id>/enrich/<connector_type>', methods=['POST'])
@login_required
@crm_required
def api_client_enrich_connector(client_id, connector_type):
    """Enrich client from a specific business data connector."""
    from field_sales.services.business_data_service import enrich_from_connector
    client = _client_repo.get_by_id(client_id)
    if not client:
        return jsonify({'success': False, 'error': 'Not found'}), 404

    data = request.get_json(silent=True) or {}
    cui = data.get('cui', '').strip()
    if not cui:
        return jsonify({'success': False, 'error': 'CUI is required'}), 400

    try:
        result = enrich_from_connector(cui, connector_type)
        if result is None:
            return jsonify({'success': False, 'error': f'Connector {connector_type} not connected or fetch failed'}), 400

        # Store enrichment data on profile
        import json as _json
        profile = _fs_repo.get_or_create_profile(client_id)
        existing = profile.get('enrichment_data') or {}
        if isinstance(existing, str):
            try:
                existing = _json.loads(existing)
            except (ValueError, TypeError):
                existing = {}
        existing[connector_type] = {
            'data': result,
            'fetched_at': __import__('datetime').datetime.now().isoformat(),
        }
        _fs_repo.update_profile(client_id, {'enrichment_data': _json.dumps(existing)})

        # Auto-extract structured fields from connector data
        _apply_connector_to_profile(client_id, connector_type, result)

        updated_profile = _fs_repo.get_or_create_profile(client_id)
        return jsonify({
            'success': True,
            'connector_type': connector_type,
            'data': result,
            'profile': updated_profile,
        })
    except Exception:
        logger.exception('Enrichment from %s failed for client %s', connector_type, client_id)
        return jsonify({'success': False, 'error': f'{connector_type} enrichment failed'}), 500


@crm_bp.route('/api/crm/clients/<int:client_id>/connectors', methods=['GET'])
@login_required
@crm_required
def api_client_connectors(client_id):
    """Get available business data connectors for enrichment."""
    from field_sales.services.business_data_service import get_connected_business_connectors
    connectors = get_connected_business_connectors()
    return jsonify({'connectors': connectors})


@crm_bp.route('/api/crm/clients/<int:client_id>/enrich-all', methods=['POST'])
@login_required
@crm_required
def api_client_enrich_all(client_id):
    """Enrich client from all connected business data connectors."""
    from field_sales.services.business_data_service import enrich_from_all_connected
    client = _client_repo.get_by_id(client_id)
    if not client:
        return jsonify({'success': False, 'error': 'Not found'}), 404

    data = request.get_json(silent=True) or {}
    cui = data.get('cui', '').strip()
    if not cui:
        return jsonify({'success': False, 'error': 'CUI is required'}), 400

    try:
        results = enrich_from_all_connected(cui)

        # Store all enrichment data on profile
        import json as _json
        profile = _fs_repo.get_or_create_profile(client_id)
        existing = profile.get('enrichment_data') or {}
        if isinstance(existing, str):
            try:
                existing = _json.loads(existing)
            except (ValueError, TypeError):
                existing = {}
        existing.update(results)
        _fs_repo.update_profile(client_id, {'enrichment_data': _json.dumps(existing)})

        # Auto-extract structured fields from each connector's data
        for conn_type, conn_result in results.items():
            conn_data = conn_result.get('data') if isinstance(conn_result, dict) else conn_result
            if conn_data:
                _apply_connector_to_profile(client_id, conn_type, conn_data)

        updated_profile = _fs_repo.get_or_create_profile(client_id)
        return jsonify({
            'success': True,
            'results': results,
            'profile': updated_profile,
        })
    except Exception:
        logger.exception('Enrich-all failed for client %s', client_id)
        return jsonify({'success': False, 'error': 'Enrichment failed'}), 500


@crm_bp.route('/api/crm/clients/<int:client_id>/lookup-cui', methods=['POST'])
@login_required
@crm_required
def api_client_lookup_cui(client_id):
    """Search for CUI by company name or Nr. Reg using connected business APIs."""
    from field_sales.services.business_data_service import search_company_by_name, detect_company_type
    client = _client_repo.get_by_id(client_id)
    if not client:
        return jsonify({'success': False, 'error': 'Not found'}), 404

    data = request.get_json(silent=True) or {}
    raw_query = data.get('query', '').strip() or client.get('display_name', '')
    if not raw_query:
        return jsonify({'success': False, 'error': 'No search query'}), 400

    # Clean name (strip nr_reg like J40/1716/2000 which pollutes search)
    clean_query, parsed_nr_reg = _parse_name_nr_reg(raw_query)
    query = clean_query or raw_query

    results = search_company_by_name(query)

    # Fallback: search by Nr. Reg. Com. if name search returned nothing
    if not results and (parsed_nr_reg or client.get('nr_reg')):
        nr_reg = parsed_nr_reg or client.get('nr_reg', '')
        results = search_company_by_name(nr_reg)

    # Fallback: local DB lookup for CUI from already-enriched companies
    if not results:
        local_match = _client_repo.find_by_normalized_name(query.lower(), include_nr_reg=True)
        if local_match and local_match.get('cui'):
            results = [{
                'cui': str(local_match['cui']),
                'name': local_match.get('display_name', ''),
                'nr_reg': local_match.get('nr_reg', ''),
                'source': 'local_db',
            }]

    # Also auto-detect company type
    detected_type = detect_company_type(client.get('display_name', ''))

    return jsonify({
        'success': True,
        'results': results,
        'detected_type': detected_type,
        'query': query,
    })


@crm_bp.route('/api/crm/clients/<int:client_id>/ai-research', methods=['POST'])
@login_required
@crm_required
def api_client_ai_research(client_id):
    """AI-powered company research — generates intelligence report."""
    from field_sales.services.business_data_service import ai_research_company, detect_company_type
    _ensure_enrichment_column()
    client = _client_repo.get_by_id(client_id)
    if not client:
        return jsonify({'success': False, 'error': 'Not found'}), 404

    # Gather all available context
    view_360 = {}
    try:
        view_360 = _fs_repo.get_360(client_id)
    except Exception:
        pass

    profile = view_360.get('profile')
    fiscal = view_360.get('fiscal')
    enrichment_data = {}
    if profile:
        ed = profile.get('enrichment_data')
        if isinstance(ed, str):
            try:
                import json as _json
                enrichment_data = _json.loads(ed)
            except (ValueError, TypeError):
                pass
        elif isinstance(ed, dict):
            enrichment_data = ed

    # Run AI research
    research = ai_research_company(client, profile, fiscal, enrichment_data)

    # Store research in enrichment_data
    if research and 'error' not in research:
        try:
            import json as _json
            profile_obj = _fs_repo.get_or_create_profile(client_id)
            existing = profile_obj.get('enrichment_data') or {}
            if isinstance(existing, str):
                try:
                    existing = _json.loads(existing)
                except (ValueError, TypeError):
                    existing = {}
            existing['ai_research'] = {
                'data': research,
                'unverified': True,
                'fetched_at': __import__('datetime').datetime.now().isoformat(),
            }
            _fs_repo.update_profile(client_id, {'enrichment_data': _json.dumps(existing)})

            # Auto-update client_type if detected as company
            detected_type = detect_company_type(client.get('display_name', ''))
            if detected_type == 'company' and client.get('client_type') != 'company':
                _client_repo.update(client_id, {'client_type': 'company'})

            # If AI suggested a CUI and profile has none, set it
            suggested_cui = research.get('suggested_cui')
            if suggested_cui and not profile_obj.get('cui'):
                _fs_repo.update_profile(client_id, {'cui': str(suggested_cui)})
        except Exception:
            logger.exception('Failed to store AI research for client %s', client_id)

    return jsonify({
        'success': True,
        'research': research,
    })


@crm_bp.route('/api/crm/clients/sanitize', methods=['GET'])
@login_required
@crm_required
def api_sanitize_scan():
    """Scan for data quality issues: wrong types and duplicates."""
    name = request.args.get('name')
    limit = request.args.get('limit', 50, type=int)

    wrong_types = _client_repo.find_wrong_types(name=name, limit=limit)
    duplicates = _client_repo.find_duplicates(name=name, limit=limit)

    # Group duplicates into merge suggestions
    merge_groups = []
    seen = set()
    for dup in duplicates:
        key = tuple(sorted([dup['id_a'], dup['id_b']]))
        if key in seen:
            continue
        seen.add(key)

        # Determine which to keep: prefer the one with more data
        a_score = sum(1 for f in ['phone_a', 'email_a', 'nr_reg_a', 'city_a'] if dup.get(f))
        b_score = sum(1 for f in ['phone_b', 'email_b', 'nr_reg_b', 'city_b'] if dup.get(f))
        keep_id = dup['id_a'] if a_score >= b_score else dup['id_b']
        remove_id = dup['id_b'] if keep_id == dup['id_a'] else dup['id_a']

        merge_groups.append({
            'client_a': {
                'id': dup['id_a'], 'display_name': dup['name_a'],
                'client_type': dup['type_a'], 'phone': dup['phone_a'],
                'email': dup['email_a'], 'nr_reg': dup['nr_reg_a'],
                'city': dup['city_a'],
            },
            'client_b': {
                'id': dup['id_b'], 'display_name': dup['name_b'],
                'client_type': dup['type_b'], 'phone': dup['phone_b'],
                'email': dup['email_b'], 'nr_reg': dup['nr_reg_b'],
                'city': dup['city_b'],
            },
            'similarity': float(dup['sim']),
            'suggested_keep_id': keep_id,
            'suggested_remove_id': remove_id,
        })

    return jsonify({
        'wrong_types': wrong_types,
        'wrong_types_count': len(wrong_types),
        'merge_suggestions': merge_groups,
        'merge_suggestions_count': len(merge_groups),
    })


@crm_bp.route('/api/crm/clients/sanitize/fix-types', methods=['POST'])
@login_required
@crm_required
def api_sanitize_fix_types():
    """Bulk fix client_type for detected wrong types."""
    data = request.get_json(silent=True) or {}
    ids = data.get('ids', [])
    if not ids or not isinstance(ids, list):
        return jsonify({'success': False, 'error': 'ids required'}), 400
    if len(ids) > 500:
        return jsonify({'success': False, 'error': 'Max 500 clients per batch'}), 400

    count = _client_repo.batch_update_type(ids, 'company')
    return jsonify({'success': True, 'affected': count})


@crm_bp.route('/api/crm/clients/<int:client_id>', methods=['DELETE'])
@login_required
@crm_required
def api_client_delete(client_id):
    if not getattr(current_user, 'can_delete_crm', False):
        return jsonify({'success': False, 'error': 'Delete permission denied'}), 403
    if _client_repo.delete(client_id):
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Not found'}), 404


@crm_bp.route('/api/crm/clients/merge', methods=['POST'])
@login_required
@crm_required
def api_merge_clients():
    data = request.get_json(silent=True) or {}
    keep_id = data.get('keep_id')
    remove_id = data.get('remove_id')
    if not keep_id or not remove_id:
        return jsonify({'success': False, 'error': 'keep_id and remove_id required'}), 400
    try:
        _client_repo.merge(keep_id, remove_id)
        return jsonify({'success': True})
    except Exception as e:
        logger.exception('Merge failed: keep=%s remove=%s', keep_id, remove_id)
        return jsonify({'success': False, 'error': str(e)[:300]}), 500


@crm_bp.route('/api/crm/clients/batch-blacklist', methods=['POST'])
@login_required
@crm_required
def api_batch_blacklist():
    if not getattr(current_user, 'can_edit_crm', False):
        return jsonify({'success': False, 'error': 'Edit permission denied'}), 403
    data = request.get_json(silent=True) or {}
    ids = data.get('ids', [])
    is_blacklisted = bool(data.get('is_blacklisted', True))
    if not ids or not isinstance(ids, list):
        return jsonify({'success': False, 'error': 'ids required'}), 400
    if len(ids) > 500:
        return jsonify({'success': False, 'error': 'Max 500 clients per batch'}), 400
    count = _client_repo.batch_blacklist(ids, is_blacklisted)
    return jsonify({'success': True, 'affected': count})


@crm_bp.route('/api/crm/clients/batch-delete', methods=['POST'])
@login_required
@crm_required
def api_batch_delete():
    if not getattr(current_user, 'can_delete_crm', False):
        return jsonify({'success': False, 'error': 'Delete permission denied'}), 403
    data = request.get_json(silent=True) or {}
    ids = data.get('ids', [])
    if not ids or not isinstance(ids, list):
        return jsonify({'success': False, 'error': 'ids required'}), 400
    if len(ids) > 500:
        return jsonify({'success': False, 'error': 'Max 500 clients per batch'}), 400
    count = _client_repo.batch_delete(ids)
    return jsonify({'success': True, 'affected': count})


@crm_bp.route('/api/crm/clients/<int:client_id>/blacklist', methods=['POST'])
@login_required
@crm_required
def api_client_toggle_blacklist(client_id):
    if not getattr(current_user, 'can_edit_crm', False):
        return jsonify({'success': False, 'error': 'Edit permission denied'}), 403
    data = request.get_json(silent=True) or {}
    is_blacklisted = bool(data.get('is_blacklisted', False))
    result = _client_repo.toggle_blacklist(client_id, is_blacklisted)
    if not result:
        return jsonify({'success': False, 'error': 'Not found'}), 404
    return jsonify({'success': True, 'client': result})


# ════════════════════════════════════════════════════════════════
# Contact persons
# ════════════════════════════════════════════════════════════════

@crm_bp.route('/api/crm/clients/<int:client_id>/contacts', methods=['GET'])
@login_required
@crm_required
def api_list_client_contacts(client_id):
    return jsonify({'contacts': _contact_repo.list_by_client(client_id)})


@crm_bp.route('/api/crm/clients/<int:client_id>/contacts', methods=['POST'])
@login_required
@crm_required
def api_create_client_contact(client_id):
    data = request.get_json(silent=True) or {}
    if not (data.get('full_name') or '').strip():
        return jsonify({'success': False, 'error': 'full_name is required'}), 400
    contact = _contact_repo.create(client_id, data)
    return jsonify({'success': True, 'contact': contact})


@crm_bp.route('/api/crm/contacts/<int:contact_id>', methods=['PUT'])
@login_required
@crm_required
def api_update_client_contact(contact_id):
    contact = _contact_repo.update(contact_id, request.get_json(silent=True) or {})
    return jsonify({'success': True, 'contact': contact})


@crm_bp.route('/api/crm/contacts/<int:contact_id>', methods=['DELETE'])
@login_required
@crm_required
def api_delete_client_contact(contact_id):
    _contact_repo.delete(contact_id)
    return jsonify({'success': True})
