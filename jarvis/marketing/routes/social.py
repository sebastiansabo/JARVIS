"""Marketing project members, comments, files routes."""

import logging
from flask import jsonify, request
from flask_login import login_required, current_user

from marketing import marketing_bp
from marketing.repositories import (
    MemberRepository, CommentRepository, FileRepository, ActivityRepository,
    KpiRepository,
)
from marketing.routes.projects import mkt_permission_required
from core.utils.api_helpers import get_json_or_error, safe_error_response

logger = logging.getLogger('jarvis.marketing.routes.social')

_member_repo = MemberRepository()
_comment_repo = CommentRepository()
_file_repo = FileRepository()
_activity_repo = ActivityRepository()
_kpi_repo = KpiRepository()


# ---- Members ----

@marketing_bp.route('/api/projects/<int:project_id>/members', methods=['GET'])
@login_required
@mkt_permission_required('project', 'view')
def api_get_members(project_id):
    """Get project team members."""
    members = _member_repo.get_by_project(project_id)
    return jsonify({'members': members})


@marketing_bp.route('/api/projects/<int:project_id>/members', methods=['POST'])
@login_required
@mkt_permission_required('project', 'edit')
def api_add_member(project_id):
    """Add a team member to a project."""
    data, error = get_json_or_error()
    if error:
        return error

    user_id = data.get('user_id')
    role = data.get('role', 'member')
    if not user_id:
        return jsonify({'success': False, 'error': 'user_id is required'}), 400

    try:
        member_id = _member_repo.add(
            project_id, user_id, role, current_user.id,
            department_structure_id=data.get('department_structure_id'),
        )
        _activity_repo.log(project_id, 'member_added', actor_id=current_user.id,
                           details={'user_id': user_id, 'role': role})

        # Notify new member
        from core.notifications.notify import notify_user
        notify_user(
            user_id,
            title='You were added to a marketing project',
            link=f'/app/marketing/projects/{project_id}',
            entity_type='mkt_project',
            entity_id=project_id,
            type='info',
        )

        return jsonify({'success': True, 'id': member_id}), 201
    except Exception as e:
        return safe_error_response(e)


@marketing_bp.route('/api/projects/<int:project_id>/members/<int:member_id>', methods=['PUT'])
@login_required
@mkt_permission_required('project', 'edit')
def api_update_member(project_id, member_id):
    """Update a member's role."""
    data, error = get_json_or_error()
    if error:
        return error

    role = data.get('role')
    if not role:
        return jsonify({'success': False, 'error': 'role is required'}), 400

    if _member_repo.update_role(member_id, role):
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Member not found'}), 404


@marketing_bp.route('/api/projects/<int:project_id>/members/<int:member_id>', methods=['DELETE'])
@login_required
@mkt_permission_required('project', 'edit')
def api_remove_member(project_id, member_id):
    """Remove a member from the project."""
    if _member_repo.remove(member_id):
        _activity_repo.log(project_id, 'member_removed', actor_id=current_user.id,
                           details={'member_id': member_id})
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Member not found'}), 404


# ---- Comments ----

@marketing_bp.route('/api/projects/<int:project_id>/comments', methods=['GET'])
@login_required
@mkt_permission_required('project', 'view')
def api_get_comments(project_id):
    """Get project comments."""
    include_internal = request.args.get('include_internal', 'false').lower() == 'true'
    comments = _comment_repo.get_by_project(project_id, include_internal=include_internal)
    return jsonify({'comments': comments})


@marketing_bp.route('/api/projects/<int:project_id>/comments', methods=['POST'])
@login_required
@mkt_permission_required('project', 'view')
def api_create_comment(project_id):
    """Add a comment to a project."""
    data, error = get_json_or_error()
    if error:
        return error

    content = data.get('content')
    if not content:
        return jsonify({'success': False, 'error': 'content is required'}), 400

    try:
        comment_id = _comment_repo.create(
            project_id, current_user.id, content,
            parent_id=data.get('parent_id'),
            is_internal=data.get('is_internal', False),
        )
        _activity_repo.log(project_id, 'comment_added', actor_id=current_user.id)
        return jsonify({'success': True, 'id': comment_id}), 201
    except Exception as e:
        return safe_error_response(e)


@marketing_bp.route('/api/comments/<int:comment_id>', methods=['PUT'])
@login_required
def api_update_comment(comment_id):
    """Update a comment (own comments only)."""
    data, error = get_json_or_error()
    if error:
        return error

    content = data.get('content')
    if not content:
        return jsonify({'success': False, 'error': 'content is required'}), 400

    if _comment_repo.update(comment_id, content):
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Comment not found'}), 404


@marketing_bp.route('/api/comments/<int:comment_id>', methods=['DELETE'])
@login_required
def api_delete_comment(comment_id):
    """Soft delete a comment."""
    if _comment_repo.soft_delete(comment_id):
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Comment not found'}), 404


# ---- Files ----

@marketing_bp.route('/api/projects/<int:project_id>/files', methods=['GET'])
@login_required
@mkt_permission_required('project', 'view')
def api_get_files(project_id):
    """Get project files."""
    files = _file_repo.get_by_project(project_id)
    return jsonify({'files': files})


@marketing_bp.route('/api/projects/<int:project_id>/files', methods=['POST'])
@login_required
@mkt_permission_required('project', 'edit')
def api_create_file(project_id):
    """Attach a file to a project."""
    data, error = get_json_or_error()
    if error:
        return error

    file_name = data.get('file_name')
    storage_uri = data.get('storage_uri')
    if not file_name or not storage_uri:
        return jsonify({'success': False, 'error': 'file_name and storage_uri are required'}), 400

    try:
        file_id = _file_repo.create(
            project_id, file_name, storage_uri, current_user.id,
            file_type=data.get('file_type'),
            mime_type=data.get('mime_type'),
            file_size=data.get('file_size'),
            description=data.get('description'),
        )
        _activity_repo.log(project_id, 'file_attached', actor_id=current_user.id,
                           details={'file_name': file_name})
        return jsonify({'success': True, 'id': file_id}), 201
    except Exception as e:
        return safe_error_response(e)


@marketing_bp.route('/api/files/<int:file_id>', methods=['DELETE'])
@login_required
def api_delete_file(file_id):
    """Delete a file attachment."""
    if _file_repo.delete(file_id):
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'File not found'}), 404


@marketing_bp.route('/api/projects/<int:project_id>/files/upload', methods=['POST'])
@login_required
@mkt_permission_required('project', 'edit')
def api_upload_file(project_id):
    """Upload a file to Google Drive and attach to project."""
    from marketing.repositories import ProjectRepository
    from core.services.drive_service import get_drive_service, find_or_create_folder, ROOT_FOLDER_ID

    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file provided'}), 400

    f = request.files['file']
    if not f.filename:
        return jsonify({'success': False, 'error': 'Empty filename'}), 400

    # 10 MB limit
    file_bytes = f.read()
    if len(file_bytes) > 10 * 1024 * 1024:
        return jsonify({'success': False, 'error': 'File exceeds 10 MB limit'}), 400

    description = request.form.get('description', '')

    try:
        # Get project name for folder structure
        proj = ProjectRepository().get_by_id(project_id)
        if not proj:
            return jsonify({'success': False, 'error': 'Project not found'}), 404

        project_name = proj.get('name', f'Project-{project_id}')
        clean_name = ''.join(c for c in project_name if c.isalnum() or c in ' -_').strip() or f'Project-{project_id}'

        service = get_drive_service()
        # Folder: Root / Marketing / {ProjectName}
        mkt_folder = find_or_create_folder(service, 'Marketing', ROOT_FOLDER_ID)
        proj_folder = find_or_create_folder(service, clean_name, mkt_folder)

        # Upload
        from googleapiclient.http import MediaIoBaseUpload
        import io as iomod
        ext = f.filename.lower().rsplit('.', 1)[-1] if '.' in f.filename else ''
        mime_map = {
            'pdf': 'application/pdf', 'jpg': 'image/jpeg', 'jpeg': 'image/jpeg',
            'png': 'image/png', 'doc': 'application/msword',
            'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'xls': 'application/vnd.ms-excel',
            'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'ppt': 'application/vnd.ms-powerpoint',
            'pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
        }
        mime_type = mime_map.get(ext, 'application/octet-stream')

        media = MediaIoBaseUpload(iomod.BytesIO(file_bytes), mimetype=mime_type, resumable=True)
        drive_file = service.files().create(
            body={'name': f.filename, 'parents': [proj_folder]},
            media_body=media,
            fields='id, webViewLink',
            supportsAllDrives=True,
        ).execute()
        drive_link = drive_file.get('webViewLink', f"https://drive.google.com/file/d/{drive_file['id']}/view")

        # Create DB record
        file_id = _file_repo.create(
            project_id, f.filename, drive_link, current_user.id,
            file_type=ext or None,
            mime_type=mime_type,
            file_size=len(file_bytes),
            description=description or None,
        )
        _activity_repo.log(project_id, 'file_attached', actor_id=current_user.id,
                           details={'file_name': f.filename})
        return jsonify({
            'success': True, 'id': file_id,
            'drive_link': drive_link,
            'file_name': f.filename,
            'file_size': len(file_bytes),
        }), 201
    except Exception as e:
        logger.exception('File upload failed')
        return safe_error_response(e)


# ---- KPIs ----

@marketing_bp.route('/api/projects/<int:project_id>/kpis', methods=['GET'])
@login_required
@mkt_permission_required('kpi', 'view')
def api_get_kpis(project_id):
    """Get project KPI targets and current values."""
    kpis = _kpi_repo.get_by_project(project_id)
    return jsonify({'kpis': kpis})


@marketing_bp.route('/api/projects/<int:project_id>/kpis', methods=['POST'])
@login_required
@mkt_permission_required('kpi', 'edit')
def api_add_kpi(project_id):
    """Add a KPI to a project."""
    data, error = get_json_or_error()
    if error:
        return error

    kpi_definition_id = data.get('kpi_definition_id')
    if not kpi_definition_id:
        return jsonify({'success': False, 'error': 'kpi_definition_id is required'}), 400

    try:
        kpi_id = _kpi_repo.add_project_kpi(
            project_id, kpi_definition_id,
            channel=data.get('channel'),
            target_value=data.get('target_value'),
            weight=data.get('weight', 50),
            threshold_warning=data.get('threshold_warning'),
            threshold_critical=data.get('threshold_critical'),
            notes=data.get('notes'),
        )
        _activity_repo.log(project_id, 'kpi_updated', actor_id=current_user.id,
                           details={'action': 'added', 'kpi_definition_id': kpi_definition_id})
        return jsonify({'success': True, 'id': kpi_id}), 201
    except Exception as e:
        if 'mkt_project_kpis_unique' in str(e):
            return jsonify({'success': False, 'error': 'This KPI is already assigned to the project'}), 409
        return safe_error_response(e)


@marketing_bp.route('/api/projects/<int:project_id>/kpis/<int:kpi_id>', methods=['PUT'])
@login_required
@mkt_permission_required('kpi', 'edit')
def api_update_kpi(project_id, kpi_id):
    """Update a project KPI."""
    data, error = get_json_or_error()
    if error:
        return error

    try:
        updated = _kpi_repo.update_project_kpi(kpi_id, **data)
        if updated:
            _activity_repo.log(project_id, 'kpi_updated', actor_id=current_user.id,
                               details={'kpi_id': kpi_id})
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': 'KPI not found'}), 404
    except Exception as e:
        return safe_error_response(e)


@marketing_bp.route('/api/projects/<int:project_id>/kpis/<int:kpi_id>', methods=['DELETE'])
@login_required
@mkt_permission_required('kpi', 'edit')
def api_delete_kpi(project_id, kpi_id):
    """Remove a KPI from a project."""
    if _kpi_repo.delete_project_kpi(kpi_id):
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'KPI not found'}), 404


@marketing_bp.route('/api/projects/<int:project_id>/kpis/<int:kpi_id>/snapshot', methods=['POST'])
@login_required
@mkt_permission_required('kpi', 'edit')
def api_add_kpi_snapshot(project_id, kpi_id):
    """Record a KPI measurement."""
    data, error = get_json_or_error()
    if error:
        return error

    value = data.get('value')
    if value is None:
        return jsonify({'success': False, 'error': 'value is required'}), 400

    try:
        snap_id = _kpi_repo.add_snapshot(
            kpi_id, value,
            recorded_by=current_user.id,
            source=data.get('source', 'manual'),
            notes=data.get('notes'),
        )
        _activity_repo.log(project_id, 'kpi_updated', actor_id=current_user.id,
                           details={'kpi_id': kpi_id, 'value': float(value)})
        return jsonify({'success': True, 'id': snap_id}), 201
    except Exception as e:
        return safe_error_response(e)


# ---- KPI Snapshots History ----

@marketing_bp.route('/api/kpi-snapshots/<int:project_kpi_id>', methods=['GET'])
@login_required
@mkt_permission_required('kpi', 'view')
def api_get_kpi_snapshots(project_kpi_id):
    """Get historical snapshots for a project KPI."""
    limit = min(int(request.args.get('limit', 50)), 200)
    snapshots = _kpi_repo.get_snapshots(project_kpi_id, limit=limit)
    return jsonify({'snapshots': snapshots})


# ---- KPI ↔ Budget Line linking ----

@marketing_bp.route('/api/kpis/<int:kpi_id>/budget-lines', methods=['GET'])
@login_required
@mkt_permission_required('kpi', 'view')
def api_get_kpi_budget_lines(kpi_id):
    """Get budget lines linked to a KPI."""
    lines = _kpi_repo.get_kpi_budget_lines(kpi_id)
    return jsonify({'budget_lines': lines})


@marketing_bp.route('/api/kpis/<int:kpi_id>/budget-lines', methods=['POST'])
@login_required
@mkt_permission_required('kpi', 'edit')
def api_link_kpi_budget_line(kpi_id):
    """Link a budget line to a KPI."""
    data, error = get_json_or_error()
    if error:
        return error
    budget_line_id = data.get('budget_line_id')
    if not budget_line_id:
        return jsonify({'success': False, 'error': 'budget_line_id is required'}), 400
    role = data.get('role', 'input')
    if not role or not isinstance(role, str) or not role.replace('_', '').isalpha():
        return jsonify({'success': False, 'error': 'role must be a valid variable name'}), 400
    try:
        link_id = _kpi_repo.link_budget_line(kpi_id, budget_line_id, role=role)
        return jsonify({'success': True, 'id': link_id}), 201
    except Exception as e:
        return safe_error_response(e)


@marketing_bp.route('/api/kpis/<int:kpi_id>/budget-lines/<int:line_id>', methods=['DELETE'])
@login_required
@mkt_permission_required('kpi', 'edit')
def api_unlink_kpi_budget_line(kpi_id, line_id):
    """Unlink a budget line from a KPI."""
    if _kpi_repo.unlink_budget_line(kpi_id, line_id):
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Link not found'}), 404


# ---- KPI ↔ KPI dependencies ----

@marketing_bp.route('/api/kpis/<int:kpi_id>/dependencies', methods=['GET'])
@login_required
@mkt_permission_required('kpi', 'view')
def api_get_kpi_dependencies(kpi_id):
    """Get KPI dependencies."""
    deps = _kpi_repo.get_kpi_dependencies(kpi_id)
    return jsonify({'dependencies': deps})


@marketing_bp.route('/api/kpis/<int:kpi_id>/dependencies', methods=['POST'])
@login_required
@mkt_permission_required('kpi', 'edit')
def api_link_kpi_dependency(kpi_id):
    """Link a KPI dependency."""
    data, error = get_json_or_error()
    if error:
        return error
    depends_on_kpi_id = data.get('depends_on_kpi_id')
    role = data.get('role', 'input')
    if not depends_on_kpi_id:
        return jsonify({'success': False, 'error': 'depends_on_kpi_id is required'}), 400
    if not role or not isinstance(role, str) or not role.replace('_', '').isalpha():
        return jsonify({'success': False, 'error': 'role must be a valid variable name'}), 400
    try:
        link_id = _kpi_repo.link_kpi_dependency(kpi_id, depends_on_kpi_id, role)
        return jsonify({'success': True, 'id': link_id}), 201
    except Exception as e:
        return safe_error_response(e)


@marketing_bp.route('/api/kpis/<int:kpi_id>/dependencies/<int:dep_kpi_id>', methods=['DELETE'])
@login_required
@mkt_permission_required('kpi', 'edit')
def api_unlink_kpi_dependency(kpi_id, dep_kpi_id):
    """Unlink a KPI dependency."""
    if _kpi_repo.unlink_kpi_dependency(kpi_id, dep_kpi_id):
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Dependency not found'}), 404


# ---- KPI Sync ----

@marketing_bp.route('/api/projects/<int:project_id>/kpis/sync-all', methods=['POST'])
@login_required
@mkt_permission_required('kpi', 'edit')
def api_sync_all_kpis(project_id):
    """Sync all KPIs for a project."""
    try:
        synced = _kpi_repo.sync_all_project_kpis(project_id)
        return jsonify({'success': True, 'synced_count': synced})
    except Exception as e:
        return safe_error_response(e)


@marketing_bp.route('/api/kpis/<int:kpi_id>/sync', methods=['POST'])
@login_required
@mkt_permission_required('kpi', 'edit')
def api_sync_kpi(kpi_id):
    """Recalculate KPI value from linked sources."""
    try:
        result = _kpi_repo.sync_kpi(kpi_id)
        return jsonify({'success': True, **result})
    except Exception as e:
        return safe_error_response(e)
