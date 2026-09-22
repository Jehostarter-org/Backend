from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender='messaging.Message')
def notify_recipient_on_new_message(sender, instance, created, **kwargs):
    """
    Fire a notification to the other participant whenever a new message is saved.
    Pushes a real-time WebSocket event via the existing NotificationConsumer group.
    """
    if not created:
        return

    conversation = instance.conversation
    recipient    = conversation.get_other_participant(instance.sender)
    if not recipient:
        return

    preview     = instance.body[:60] if instance.body else '📎 Sent an attachment'
    sender_name = instance.sender.get_full_name() or instance.sender.email

    # A support thread routes the user straight to /support; a normal DM goes to
    # the community message thread. Any admin whose support reply reaches the
    # customer should be surfaced as a support message notification.
    is_support    = conversation.is_support()
    notif_type    = 'support_message' if is_support else 'direct_message'
    link          = '/support/' if is_support else f'/messages/{conversation.id}/'
    title         = 'New support message' if is_support else f'New message from {sender_name}'

    try:
        from notifications.models import Notification
        notif = Notification.objects.create(
            recipient         = recipient,
            actor             = instance.sender,
            notification_type = notif_type,
            title             = title,
            message           = preview,
            link              = link,
        )

        # Push real-time WebSocket event using the existing NotificationConsumer
        # group pattern: user_notifications_{user_id}
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer

        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f'user_notifications_{recipient.id}',
            {
                'type': 'new_notification',
                'payload': {
                    'id':                str(notif.id),
                    'notification_type': notif_type,
                    'title':             notif.title,
                    'message':           notif.message,
                    'link':              notif.link,
                    'conversation_id':   conversation.id,
                    'sender_id':         instance.sender.id,
                    'sender_name':       sender_name,
                },
            }
        )
    except Exception as e:
        # Never let a notification failure break message delivery
        import logging
        logging.getLogger(__name__).warning('DM notification failed: %s', e)
