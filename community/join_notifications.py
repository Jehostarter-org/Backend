"""
Community join-request notifications.

Notifies admins when someone requests to join their community and the
applicant when the request is approved/rejected. Rows are always persisted
first — the notification page reads from the DB — then pushed live over the
existing NotificationConsumer group (`new_notification` event).
"""

from django.utils import timezone

from notifications.models import Notification

from .broadcast import broadcast_to_user
from .models import CommunityMember


def notify_admins_of_join_request(community, requester, member):
    """Persist one join-request notification per community admin/moderator."""
    admins = CommunityMember.objects.filter(
        community=community,
        role__in=['admin', 'moderator'],
        status='approved',
        is_banned=False,
    ).select_related('user')

    for admin_member in admins:
        notif = Notification.objects.create(
            recipient=admin_member.user,
            actor=requester,
            notification_type='community_join_request',
            title=f'{requester.username} wants to join {community.name}',
            message=f'{requester.username} has requested to join {community.name}.',
            link=f'/dashboard/community?group={community.pk}',
            data={
                'community_id': str(community.pk),
                'member_id': str(member.pk),
                'username': requester.username,
            },
        )
        _push(notif)


def notify_join_result(member, community, approved):
    """Tell the applicant their join request was approved or rejected."""
    verb = 'approved' if approved else 'rejected'
    notif = Notification.objects.create(
        recipient=member.user,
        notification_type='community_join_result',
        title=f'Join request {verb}',
        message=f'Your request to join {community.name} has been {verb}.',
        link=f'/dashboard/community?group={community.pk}',
        data={'community_id': str(community.pk), 'approved': approved},
    )
    _push(notif)


def clear_join_request_notifications(community_id, member_id):
    """Mark every admin's notification for this join request as read.

    Runs after the request is approved/rejected so no admin is left with
    stale Accept/Decline buttons on their notification page.
    """
    Notification.objects.filter(
        notification_type='community_join_request',
        data__community_id=str(community_id),
        data__member_id=str(member_id),
        is_read=False,
    ).update(is_read=True, read_at=timezone.now())


def _push(notif):
    broadcast_to_user(str(notif.recipient_id), 'new_notification', {
        'payload': {
            'notification_id': notif.id,
            'type': notif.notification_type,
            'title': notif.title,
            'message': notif.message,
            'link': notif.link,
            'created_at': notif.created_at.isoformat(),
            'data': notif.data,
        },
    })
