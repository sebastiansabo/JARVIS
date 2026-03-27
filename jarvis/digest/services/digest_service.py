"""Service layer for the Digest module."""

import re
import logging
from digest.repositories.digest_repository import DigestRepository

logger = logging.getLogger(__name__)
_repo = DigestRepository()

# Matches @[Display Name](user_id)
_MENTION_RE = re.compile(r'@\[([^\]]+)\]\((\d+)\)')


class DigestService:

    # ── Channels ─────────────────────────────────────────────

    def get_channels(self, user_id):
        return _repo.get_channels(user_id)

    def get_channel(self, channel_id):
        return _repo.get_channel(channel_id)

    def create_channel(self, name, description, channel_type, is_private, created_by, targets=None):
        channel = _repo.create_channel(name, description, channel_type, is_private, created_by)
        if channel:
            _repo.add_member(channel['id'], created_by, 'admin')
            if targets:
                _repo.set_channel_targets(channel['id'], targets)
                _repo.sync_members_from_targets(channel['id'])
            logger.info(f'Channel created: {channel["id"]} by user {created_by}')
        return channel

    def update_channel(self, channel_id, name, description):
        return _repo.update_channel(channel_id, name, description)

    def delete_channel(self, channel_id):
        return _repo.delete_channel(channel_id)

    # ── Members ──────────────────────────────────────────────

    def get_channel_members(self, channel_id):
        return _repo.get_channel_members(channel_id)

    def add_member(self, channel_id, user_id, role='member'):
        return _repo.add_member(channel_id, user_id, role)

    def remove_member(self, channel_id, user_id):
        return _repo.remove_member(channel_id, user_id)

    def set_member_role(self, channel_id, user_id, role):
        return _repo.set_member_role(channel_id, user_id, role)

    def search_users(self, query):
        return _repo.search_users(query)

    def can_access_channel(self, channel_id, user_id):
        channel = _repo.get_channel(channel_id)
        if not channel:
            return False
        if not channel['is_private']:
            return True
        return _repo.is_member(channel_id, user_id)

    def is_admin_or_moderator(self, channel_id, user_id):
        members = _repo.get_channel_members(channel_id)
        for m in members:
            if m['user_id'] == user_id and m['role'] in ('admin', 'moderator'):
                return True
        return False

    # ── Channel Targets ──────────────────────────────────────

    def get_channel_targets(self, channel_id):
        return _repo.get_channel_targets(channel_id)

    def update_channel_targets(self, channel_id, targets):
        _repo.set_channel_targets(channel_id, targets)
        _repo.sync_members_from_targets(channel_id)

    # ── Channel Settings ─────────────────────────────────────

    def update_channel_settings(self, channel_id, settings):
        return _repo.update_channel_settings(channel_id, settings)

    def clear_channel_history(self, channel_id):
        return _repo.clear_channel_history(channel_id)

    # ── Posts ────────────────────────────────────────────────

    def get_posts(self, channel_id, limit=50, offset=0, parent_id=None):
        posts = _repo.get_posts(channel_id, limit, offset, parent_id)
        for post in posts:
            post['reactions'] = _repo.get_reactions(post['id'])
            if post['type'] == 'poll':
                post['poll'] = _repo.get_poll(post['id'])
        return posts

    def get_post(self, post_id):
        post = _repo.get_post(post_id)
        if post:
            post['reactions'] = _repo.get_reactions(post_id)
            if post['type'] == 'poll':
                post['poll'] = _repo.get_poll(post_id)
        return post

    def create_post(self, channel_id, user_id, content, post_type='post',
                    parent_id=None, reply_to_id=None, poll_data=None,
                    author_name=None):
        post = _repo.create_post(channel_id, user_id, content, post_type, parent_id, reply_to_id)
        if post and post_type == 'poll' and poll_data:
            _repo.create_poll(
                post['id'],
                poll_data['question'],
                poll_data['options'],
                poll_data.get('is_multiple_choice', False),
                poll_data.get('closes_at'),
            )
        logger.info(f'Post created: {post["id"]} in channel {channel_id} by user {user_id}')

        # Send notifications (non-blocking)
        if post:
            try:
                self._notify_post(post, channel_id, user_id, content, post_type,
                                  author_name or 'Someone', poll_data)
            except Exception as e:
                logger.error(f'Post notification failed: {e}')

        return post

    def _notify_post(self, post, channel_id, user_id, content, post_type,
                     author_name, poll_data):
        """Send push + in-app notifications for a new post."""
        from core.notifications.notify import notify_with_push

        channel = _repo.get_channel(channel_id)
        if not channel:
            return

        channel_name = channel['name']
        members = _repo.get_channel_members(channel_id)
        member_ids = {m['user_id'] for m in members}
        push_data = {'channel_id': str(channel_id), 'type': 'digest'}

        notified_ids = set()

        # 1. Announcement channels → notify all members
        if channel['type'] == 'announcement':
            targets = member_ids - {user_id}
            if targets:
                notify_with_push(
                    list(targets),
                    f'📢 {channel_name}',
                    message=f'{author_name}: {content[:120]}',
                    link=f'/app/digest?channel={channel_id}',
                    entity_type='digest_post', entity_id=post['id'],
                    push_data=push_data,
                )
                notified_ids.update(targets)

        # 2. Polls → notify all members
        if post_type == 'poll':
            question = poll_data['question'] if poll_data else content
            targets = member_ids - {user_id} - notified_ids
            if targets:
                notify_with_push(
                    list(targets),
                    f'📊 New poll in #{channel_name}',
                    message=f'{author_name}: {question[:120]}',
                    link=f'/app/digest?channel={channel_id}',
                    entity_type='digest_poll', entity_id=post['id'],
                    push_data=push_data,
                )
                notified_ids.update(targets)

        # 3. @mentions → notify mentioned users
        mentioned_ids = self._extract_mention_ids(content)
        if mentioned_ids:
            # Only notify channel members who haven't been notified yet
            targets = (set(mentioned_ids) & member_ids) - {user_id} - notified_ids
            if targets:
                notify_with_push(
                    list(targets),
                    f'{author_name} mentioned you in #{channel_name}',
                    message=content[:120],
                    link=f'/app/digest?channel={channel_id}',
                    entity_type='digest_mention', entity_id=post['id'],
                    push_data=push_data,
                )
                notified_ids.update(targets)

        # 4. Regular posts → notify all members (if nobody was notified yet)
        if channel['type'] != 'announcement' and post_type != 'poll' and not notified_ids:
            targets = member_ids - {user_id}
            if targets:
                notify_with_push(
                    list(targets),
                    f'#{channel_name}',
                    message=f'{author_name}: {content[:120]}',
                    link=f'/app/digest?channel={channel_id}',
                    entity_type='digest_post', entity_id=post['id'],
                    push_data=push_data,
                )
                notified_ids.update(targets)

        # 5. Replies → notify the original post author
        parent_id = post.get('parent_id')
        if parent_id:
            parent_post = _repo.get_post(parent_id)
            if parent_post and parent_post['user_id'] != user_id:
                reply_target = {parent_post['user_id']} - notified_ids
                if reply_target:
                    notify_with_push(
                        list(reply_target),
                        f'{author_name} replied to your post in #{channel_name}',
                        message=content[:120],
                        link=f'/app/digest?channel={channel_id}&parent={parent_id}',
                        entity_type='digest_reply', entity_id=post['id'],
                        push_data=push_data,
                    )

    @staticmethod
    def _extract_mention_ids(content):
        """Extract user IDs from @[Name](id) patterns in content."""
        if not content:
            return []
        return [int(m.group(2)) for m in _MENTION_RE.finditer(content)]

    def update_post(self, post_id, content, user_id):
        post = _repo.get_post(post_id)
        if not post or post['user_id'] != user_id:
            return None
        return _repo.update_post(post_id, content)

    def delete_post(self, post_id, user_id):
        post = _repo.get_post(post_id)
        if not post or post['user_id'] != user_id:
            return False
        _repo.delete_post(post_id)
        return True

    def toggle_pin(self, post_id):
        return _repo.toggle_pin(post_id)

    # ── Reactions ────────────────────────────────────────────

    def toggle_reaction(self, post_id, user_id, emoji):
        return _repo.toggle_reaction(post_id, user_id, emoji)

    # ── Polls ────────────────────────────────────────────────

    def get_poll(self, post_id, user_id=None):
        poll = _repo.get_poll(post_id)
        if poll and user_id:
            votes = _repo.get_user_votes(poll['id'], user_id)
            poll['user_votes'] = [v['option_id'] for v in votes]
        return poll

    def vote(self, poll_id, option_id, user_id):
        return _repo.vote(poll_id, option_id, user_id)

    def unvote(self, poll_id, option_id, user_id):
        return _repo.unvote(poll_id, option_id, user_id)

    # ── Read Status ──────────────────────────────────────────

    def mark_read(self, channel_id, user_id, post_id):
        return _repo.mark_read(channel_id, user_id, post_id)

    def get_unread_counts(self, user_id):
        return _repo.get_unread_counts(user_id)
