"""Ticketing API routes."""
import logging
from flask import request, jsonify, g
from flask_login import login_required, current_user

from ticketing import ticketing_bp
from ticketing.repositories.ticket_repository import TicketRepository, TicketCommentRepository
from core.utils.api_helpers import error_response, safe_error_response, get_json_or_error
from core.roles.decorators import v2_permission_required
from core.notifications.notify import notify_user

logger = logging.getLogger('jarvis.ticketing.routes')

_ticket_repo = TicketRepository()
_comment_repo = TicketCommentRepository()


def _is_it_staff():
    """Check if current user has ticketing.ticket.manage permission."""
    if getattr(current_user, 'is_admin', False) or getattr(current_user, 'can_access_settings', False):
        return True
    role_id = getattr(current_user, 'role_id', None)
    if not role_id:
        return False
    from core.roles.repositories import PermissionRepository
    perm = PermissionRepository().check_permission_v2(role_id, 'ticketing', 'ticket', 'manage')
    return perm.get('has_permission', False)


# ---- Stats ----

@ticketing_bp.route('/api/tickets/stats', methods=['GET'])
@login_required
def api_ticket_stats():
    """Get ticket counts by status."""
    try:
        if _is_it_staff():
            stats = _ticket_repo.get_stats()
        else:
            stats = _ticket_repo.get_stats(created_by=current_user.id)
        return jsonify({'success': True, **stats})
    except Exception as e:
        return safe_error_response(e)


# ---- List / Create ----

@ticketing_bp.route('/api/tickets', methods=['GET'])
@login_required
def api_list_tickets():
    """List tickets with filters."""
    try:
        status = request.args.get('status')
        priority = request.args.get('priority')
        category = request.args.get('category')
        assigned_to = request.args.get('assigned_to', type=int)
        search = request.args.get('search')
        my_tickets = request.args.get('my_tickets', '').lower() == 'true'
        limit = min(request.args.get('limit', 50, type=int), 200)
        offset = request.args.get('offset', 0, type=int)

        created_by = None
        if my_tickets or not _is_it_staff():
            created_by = current_user.id

        result = _ticket_repo.get_all(
            status=status, priority=priority, category=category,
            assigned_to=assigned_to, created_by=created_by,
            search=search, limit=limit, offset=offset,
        )
        return jsonify({'success': True, **result})
    except Exception as e:
        return safe_error_response(e)


@ticketing_bp.route('/api/tickets', methods=['POST'])
@login_required
def api_create_ticket():
    """Create a new ticket."""
    try:
        data, err = get_json_or_error()
        if err:
            return err

        title = (data.get('title') or '').strip()
        if not title:
            return error_response('Title is required')

        description = (data.get('description') or '').strip() or None
        priority = data.get('priority', 'medium')
        category = data.get('category', 'other')

        if priority not in ('low', 'medium', 'high', 'critical'):
            return error_response('Invalid priority')
        if category not in ('hardware', 'software', 'network', 'access', 'other'):
            return error_response('Invalid category')

        ticket = _ticket_repo.create(
            title=title,
            description=description,
            priority=priority,
            category=category,
            created_by=current_user.id,
        )

        return jsonify({'success': True, 'id': ticket['id'], 'ticket': ticket})
    except Exception as e:
        return safe_error_response(e)


# ---- Single Ticket ----

@ticketing_bp.route('/api/tickets/<int:ticket_id>', methods=['GET'])
@login_required
def api_get_ticket(ticket_id):
    """Get ticket detail with comments."""
    try:
        ticket = _ticket_repo.get_by_id(ticket_id)
        if not ticket:
            return error_response('Ticket not found', 404)

        # Access control: creator or IT staff
        if ticket['created_by'] != current_user.id and not _is_it_staff():
            return error_response('Permission denied', 403)

        comments = _comment_repo.get_by_ticket(ticket_id)
        return jsonify({'success': True, 'ticket': ticket, 'comments': comments})
    except Exception as e:
        return safe_error_response(e)


@ticketing_bp.route('/api/tickets/<int:ticket_id>', methods=['PUT'])
@login_required
def api_update_ticket(ticket_id):
    """Update ticket (status, priority, assignment, etc.)."""
    try:
        ticket = _ticket_repo.get_by_id(ticket_id)
        if not ticket:
            return error_response('Ticket not found', 404)

        is_creator = ticket['created_by'] == current_user.id
        is_staff = _is_it_staff()

        if not is_creator and not is_staff:
            return error_response('Permission denied', 403)

        data, err = get_json_or_error()
        if err:
            return err

        updates = {}
        old_status = ticket['status']
        old_assigned = ticket['assigned_to']

        # Creator can only close their own resolved ticket
        if is_creator and not is_staff:
            new_status = data.get('status')
            if new_status and new_status == 'closed' and old_status == 'resolved':
                updates['status'] = 'closed'
            elif new_status:
                return error_response('You can only close a resolved ticket')
        else:
            # IT staff can update everything
            for field in ('title', 'description', 'status', 'priority', 'category', 'assigned_to'):
                if field in data:
                    updates[field] = data[field]

        if not updates:
            return error_response('No valid fields to update')

        _ticket_repo.update(ticket_id, **updates)

        # Notifications
        new_status = updates.get('status')
        new_assigned = updates.get('assigned_to')

        if new_assigned and new_assigned != old_assigned:
            notify_user(
                new_assigned,
                f'Ticket #{ticket_id} assigned to you',
                message=ticket['title'],
                link=f'/app/ticketing/{ticket_id}',
                entity_type='ticket', entity_id=ticket_id,
                type='info', category='ticketing',
            )

        if new_status and new_status != old_status:
            notify_user(
                ticket['created_by'],
                f'Ticket #{ticket_id} is now {new_status.replace("_", " ")}',
                message=ticket['title'],
                link=f'/app/ticketing/{ticket_id}',
                entity_type='ticket', entity_id=ticket_id,
                type='info', category='ticketing',
            )

        return jsonify({'success': True})
    except Exception as e:
        return safe_error_response(e)


@ticketing_bp.route('/api/tickets/<int:ticket_id>', methods=['DELETE'])
@login_required
def api_delete_ticket(ticket_id):
    """Delete ticket (IT staff only)."""
    try:
        if not _is_it_staff():
            return error_response('Permission denied', 403)

        ticket = _ticket_repo.get_by_id(ticket_id)
        if not ticket:
            return error_response('Ticket not found', 404)

        _ticket_repo.delete(ticket_id)
        return jsonify({'success': True})
    except Exception as e:
        return safe_error_response(e)


# ---- Comments ----

@ticketing_bp.route('/api/tickets/<int:ticket_id>/comments', methods=['POST'])
@login_required
def api_add_comment(ticket_id):
    """Add comment to a ticket."""
    try:
        ticket = _ticket_repo.get_by_id(ticket_id)
        if not ticket:
            return error_response('Ticket not found', 404)

        is_creator = ticket['created_by'] == current_user.id
        if not is_creator and not _is_it_staff():
            return error_response('Permission denied', 403)

        data, err = get_json_or_error()
        if err:
            return err

        content = (data.get('content') or '').strip()
        if not content:
            return error_response('Comment content is required')

        comment = _comment_repo.create(ticket_id, current_user.id, content)

        # Notify the other party
        if is_creator and ticket['assigned_to']:
            notify_user(
                ticket['assigned_to'],
                f'New comment on Ticket #{ticket_id}',
                message=content[:100],
                link=f'/app/ticketing/{ticket_id}',
                entity_type='ticket', entity_id=ticket_id,
                type='info', category='ticketing',
            )
        elif not is_creator:
            notify_user(
                ticket['created_by'],
                f'New comment on Ticket #{ticket_id}',
                message=content[:100],
                link=f'/app/ticketing/{ticket_id}',
                entity_type='ticket', entity_id=ticket_id,
                type='info', category='ticketing',
            )

        return jsonify({'success': True, 'comment': comment})
    except Exception as e:
        return safe_error_response(e)


@ticketing_bp.route('/api/tickets/<int:ticket_id>/comments/<int:comment_id>', methods=['DELETE'])
@login_required
def api_delete_comment(ticket_id, comment_id):
    """Delete own comment."""
    try:
        comment = _comment_repo.get_by_id(comment_id)
        if not comment:
            return error_response('Comment not found', 404)
        if comment['user_id'] != current_user.id and not _is_it_staff():
            return error_response('Permission denied', 403)

        _comment_repo.delete(comment_id)
        return jsonify({'success': True})
    except Exception as e:
        return safe_error_response(e)


# ---- IT Staff list (for assignment dropdown) ----

@ticketing_bp.route('/api/users/it-staff', methods=['GET'])
@login_required
def api_get_it_staff():
    """Get users who can be assigned tickets.

    For v1, returns all users with admin/settings access since we don't have
    a dedicated IT role yet. This can be refined later.
    """
    try:
        from core.base_repository import BaseRepository
        repo = BaseRepository()
        users = repo.query_all('''
            SELECT u.id, u.name
            FROM users u
            WHERE u.is_active = TRUE
              AND (u.can_access_settings = TRUE
                   OR EXISTS (
                       SELECT 1 FROM permissions_v2 p
                       JOIN roles r ON r.id = p.role_id
                       WHERE r.id = u.role_id
                         AND p.module = 'ticketing'
                         AND p.entity = 'ticket'
                         AND p.action = 'manage'
                         AND p.has_permission = TRUE
                   ))
            ORDER BY u.name
        ''')
        return jsonify({'success': True, 'users': users})
    except Exception:
        # Fallback: return all active users if permissions_v2 table doesn't exist yet
        try:
            from core.base_repository import BaseRepository
            repo = BaseRepository()
            users = repo.query_all('''
                SELECT u.id, u.name FROM users u
                WHERE u.is_active = TRUE
                ORDER BY u.name
            ''')
            return jsonify({'success': True, 'users': users})
        except Exception as e:
            return safe_error_response(e)
