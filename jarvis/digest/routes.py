"""Digest module API routes."""

from flask import request, jsonify
from flask_login import login_required, current_user
from digest import digest_bp
from digest.services.digest_service import DigestService

_svc = DigestService()


# ── Channels ─────────────────────────────────────────────

@digest_bp.route('/api/digest/channels', methods=['GET'])
@login_required
def list_channels():
    channels = _svc.get_channels(current_user.id)
    return jsonify({'success': True, 'data': channels})


@digest_bp.route('/api/digest/channels/<int:channel_id>', methods=['GET'])
@login_required
def get_channel(channel_id):
    if not _svc.can_access_channel(channel_id, current_user.id):
        return jsonify({'success': False, 'error': 'Access denied'}), 403
    channel = _svc.get_channel(channel_id)
    if not channel:
        return jsonify({'success': False, 'error': 'Channel not found'}), 404
    return jsonify({'success': True, 'data': channel})


@digest_bp.route('/api/digest/channels', methods=['POST'])
@login_required
def create_channel():
    data = request.get_json()
    if not data or not data.get('name'):
        return jsonify({'success': False, 'error': 'Name is required'}), 400
    channel = _svc.create_channel(
        name=data['name'],
        description=data.get('description', ''),
        channel_type=data.get('type', 'general'),
        is_private=data.get('is_private', False),
        created_by=current_user.id,
    )
    return jsonify({'success': True, 'data': channel}), 201


@digest_bp.route('/api/digest/channels/<int:channel_id>', methods=['PUT'])
@login_required
def update_channel(channel_id):
    data = request.get_json()
    if not data or not data.get('name'):
        return jsonify({'success': False, 'error': 'Name is required'}), 400
    channel = _svc.update_channel(channel_id, data['name'], data.get('description', ''))
    return jsonify({'success': True, 'data': channel})


@digest_bp.route('/api/digest/channels/<int:channel_id>', methods=['DELETE'])
@login_required
def delete_channel(channel_id):
    _svc.delete_channel(channel_id)
    return jsonify({'success': True})


# ── Channel Members ──────────────────────────────────────

@digest_bp.route('/api/digest/channels/<int:channel_id>/members', methods=['GET'])
@login_required
def list_members(channel_id):
    members = _svc.get_channel_members(channel_id)
    return jsonify({'success': True, 'data': members})


@digest_bp.route('/api/digest/channels/<int:channel_id>/members', methods=['POST'])
@login_required
def add_member(channel_id):
    data = request.get_json()
    if not data or not data.get('user_id'):
        return jsonify({'success': False, 'error': 'user_id is required'}), 400
    member = _svc.add_member(channel_id, data['user_id'], data.get('role', 'member'))
    return jsonify({'success': True, 'data': member}), 201


@digest_bp.route('/api/digest/channels/<int:channel_id>/members/<int:user_id>', methods=['DELETE'])
@login_required
def remove_member(channel_id, user_id):
    _svc.remove_member(channel_id, user_id)
    return jsonify({'success': True})


# ── Posts ────────────────────────────────────────────────

@digest_bp.route('/api/digest/channels/<int:channel_id>/posts', methods=['GET'])
@login_required
def list_posts(channel_id):
    if not _svc.can_access_channel(channel_id, current_user.id):
        return jsonify({'success': False, 'error': 'Access denied'}), 403
    limit = request.args.get('limit', 50, type=int)
    offset = request.args.get('offset', 0, type=int)
    parent_id = request.args.get('parent_id', type=int)
    posts = _svc.get_posts(channel_id, limit, offset, parent_id)
    return jsonify({'success': True, 'data': posts})


@digest_bp.route('/api/digest/posts/<int:post_id>', methods=['GET'])
@login_required
def get_post(post_id):
    post = _svc.get_post(post_id)
    if not post:
        return jsonify({'success': False, 'error': 'Post not found'}), 404
    return jsonify({'success': True, 'data': post})


@digest_bp.route('/api/digest/channels/<int:channel_id>/posts', methods=['POST'])
@login_required
def create_post(channel_id):
    if not _svc.can_access_channel(channel_id, current_user.id):
        return jsonify({'success': False, 'error': 'Access denied'}), 403
    data = request.get_json()
    if not data or not data.get('content'):
        return jsonify({'success': False, 'error': 'Content is required'}), 400
    post = _svc.create_post(
        channel_id=channel_id,
        user_id=current_user.id,
        content=data['content'],
        post_type=data.get('type', 'post'),
        parent_id=data.get('parent_id'),
        reply_to_id=data.get('reply_to_id'),
        poll_data=data.get('poll'),
    )
    return jsonify({'success': True, 'data': post}), 201


@digest_bp.route('/api/digest/posts/<int:post_id>', methods=['PUT'])
@login_required
def update_post(post_id):
    data = request.get_json()
    if not data or not data.get('content'):
        return jsonify({'success': False, 'error': 'Content is required'}), 400
    post = _svc.update_post(post_id, data['content'], current_user.id)
    if not post:
        return jsonify({'success': False, 'error': 'Not found or not authorized'}), 404
    return jsonify({'success': True, 'data': post})


@digest_bp.route('/api/digest/posts/<int:post_id>', methods=['DELETE'])
@login_required
def delete_post(post_id):
    ok = _svc.delete_post(post_id, current_user.id)
    if not ok:
        return jsonify({'success': False, 'error': 'Not found or not authorized'}), 404
    return jsonify({'success': True})


@digest_bp.route('/api/digest/posts/<int:post_id>/pin', methods=['POST'])
@login_required
def toggle_pin(post_id):
    post = _svc.toggle_pin(post_id)
    if not post:
        return jsonify({'success': False, 'error': 'Post not found'}), 404
    return jsonify({'success': True, 'data': post})


# ── Reactions ────────────────────────────────────────────

@digest_bp.route('/api/digest/posts/<int:post_id>/reactions', methods=['POST'])
@login_required
def toggle_reaction(post_id):
    data = request.get_json()
    if not data or not data.get('emoji'):
        return jsonify({'success': False, 'error': 'Emoji is required'}), 400
    action = _svc.toggle_reaction(post_id, current_user.id, data['emoji'])
    return jsonify({'success': True, 'data': {'action': action}})


# ── Polls ────────────────────────────────────────────────

@digest_bp.route('/api/digest/posts/<int:post_id>/poll', methods=['GET'])
@login_required
def get_poll(post_id):
    poll = _svc.get_poll(post_id, current_user.id)
    if not poll:
        return jsonify({'success': False, 'error': 'Poll not found'}), 404
    return jsonify({'success': True, 'data': poll})


@digest_bp.route('/api/digest/polls/<int:poll_id>/vote', methods=['POST'])
@login_required
def vote(poll_id):
    data = request.get_json()
    if not data or not data.get('option_id'):
        return jsonify({'success': False, 'error': 'option_id is required'}), 400
    result = _svc.vote(poll_id, data['option_id'], current_user.id)
    return jsonify({'success': True, 'data': result})


@digest_bp.route('/api/digest/polls/<int:poll_id>/unvote', methods=['POST'])
@login_required
def unvote(poll_id):
    data = request.get_json()
    if not data or not data.get('option_id'):
        return jsonify({'success': False, 'error': 'option_id is required'}), 400
    _svc.unvote(poll_id, data['option_id'], current_user.id)
    return jsonify({'success': True})


# ── Read Status ──────────────────────────────────────────

@digest_bp.route('/api/digest/channels/<int:channel_id>/read', methods=['POST'])
@login_required
def mark_read(channel_id):
    data = request.get_json()
    post_id = data.get('post_id') if data else None
    if not post_id:
        return jsonify({'success': False, 'error': 'post_id is required'}), 400
    _svc.mark_read(channel_id, current_user.id, post_id)
    return jsonify({'success': True})


@digest_bp.route('/api/digest/unread', methods=['GET'])
@login_required
def unread_counts():
    counts = _svc.get_unread_counts(current_user.id)
    return jsonify({'success': True, 'data': counts})
