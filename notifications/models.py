from ulid import ULID
from django.db import models
from django.conf import settings


def generate_ulid():
    return str(ULID())


class Notification(models.Model):
    """All activity notifications across the platform."""
    id = models.CharField(primary_key=True, max_length=26, default=generate_ulid, editable=False)

    NOTIF_TYPES = [
        ('community_post',    'New Community Post'),
        ('community_message', 'New Community Message'),
        ('comment',           'Comment on Post'),
        ('like',              'Post Liked'),
        ('mention',           'You were Mentioned'),
        ('community_invite',  'Community Invite'),
        ('service_accepted',  'Service Accepted'),
        ('service_updated',   'Service Updated'),
        ('service_completed', 'Service Completed'),
        ('service_cancelled', 'Service Cancelled'),
        ('shop_inquiry',      'Shop Inquiry'),
        ('boost_approved',    'Boost Approved'),
        ('boost_expired',     'Boost Expired'),
        ('membership_expiry', 'Membership Expiring Soon'),
        ('membership_expired','Membership Expired'),
        ('pickup_reminder',   'Airport Pickup Reminder'),
        ('system',            'System Notification'),
    ]

    recipient         = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')
    actor             = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='sent_notifications')
    notification_type = models.CharField(max_length=30, choices=NOTIF_TYPES)
    title             = models.CharField(max_length=200)
    message           = models.TextField()
    is_read           = models.BooleanField(default=False)
    read_at           = models.DateTimeField(null=True, blank=True)
    link              = models.CharField(max_length=300, blank=True)
    created_at        = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'notifications'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.notification_type} → {self.recipient}"
