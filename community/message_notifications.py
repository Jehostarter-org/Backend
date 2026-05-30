"""
Notify community members when a new chat message is posted.

Persists Notification rows (for inactive users) and pushes to the recipient's
notification WebSocket group (for users who are online but not in the chat).
"""

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from community.models import CommunityMember
from notifications.models import Notification

channel_layer = get_channel_layer()


def _broadcast(group: str, event_type: str, payload: dict):
    async_to_sync(channel_layer.group_send)(
        group,
        {'type': event_type, 'payload': payload},
    )


def notify_community_members(message):
    """Notify every community member except the sender."""
    community = message.community
    preview = (message.content or message.attachment_name or 'Shared a file').strip()
    if not preview:
        preview = 'New message'
    preview = preview[:100]

    title = f'{message.sender.username} in {community.name}'
    link = f'/dashboard/community?group={community.id}'

    members = (
        CommunityMember.objects
        .filter(community=community, is_banned=False)
        .exclude(user_id=message.sender_id)
        .select_related('user')
    )

    for member in members:
        notif = Notification.objects.create(
            recipient=member.user,
            actor=message.sender,
            notification_type='community_message',
            title=title,
            message=preview,
            link=link,
        )
        _broadcast(
            group=f'user_notifications_{member.user_id}',
            event_type='new_notification',
            payload={
                'notification_id': notif.id,
                'type': notif.notification_type,
                'title': notif.title,
                'message': notif.message,
                'link': notif.link,
                'created_at': notif.created_at.isoformat(),
            },
        )
