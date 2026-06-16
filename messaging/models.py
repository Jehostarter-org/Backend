from django.db import models
from django.conf import settings
from django.utils import timezone


class Conversation(models.Model):
    """
    A DM thread between exactly two users.
    Optionally linked to a service booking or shop listing
    so that a service card is auto-attached to the thread.
    """
    participants = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='conversations',
    )

    # Optional context links — set when the DM is opened from a service or shop
    service_type = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        choices=[
            ('airport_pickup',      'Airport Pickup'),
            ('home_inspection',     'Home Inspection'),
            ('chaperone',           'Chaperone'),
            ('temporary_housing',   'Temporary Housing'),
            ('migration_specialist','Migration Specialist'),
        ],
        help_text='If this conversation was started from a service, record which one.',
    )
    # Generic FK approach: store IDs loosely so we can link shop items or
    # service bookings without hard coupling.
    linked_object_type = models.CharField(max_length=50, blank=True, null=True)
    linked_object_id   = models.CharField(max_length=64, blank=True, null=True)

    # Currency context — captured from the initiating user's location at creation
    currency_code = models.CharField(max_length=3, blank=True, null=True,
        help_text='e.g. AUD, NGN, GBP — currency active when thread was created')
    location_country = models.CharField(max_length=2, blank=True, null=True,
        help_text='ISO 3166-1 alpha-2 country code of the initiating user')

    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)  # bumped on every new message

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        names = ', '.join(p.get_full_name() or p.email for p in self.participants.all())
        return f'Conversation({names})'

    def get_other_participant(self, user):
        return self.participants.exclude(pk=user.pk).first()

    def unread_count_for(self, user):
        return self.messages.filter(is_read=False).exclude(sender=user).count()


class Message(models.Model):
    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name='messages',
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='sent_messages',
    )
    reply_to = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='replies',
    )
    body = models.TextField(blank=True)
    is_read     = models.BooleanField(default=False)
    read_at     = models.DateTimeField(null=True, blank=True)
    created_at  = models.DateTimeField(auto_now_add=True)

    # Service card data — populated when conversation has a service_type
    # Stored as a snapshot so it stays accurate even if the booking changes later
    service_card = models.JSONField(
        null=True, blank=True,
        help_text=(
            'Snapshot of service details shown as a card in the thread. '
            'e.g. {"title": "Brisbane Airport → Sunnybank", "date": "2026-06-04", '
            '"price": 45, "currency": "AUD", "service_type": "airport_pickup"}'
        ),
    )

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        preview = self.body[:40] if self.body else '[attachment]'
        return f'Message from {self.sender_id}: {preview}'

    def mark_read(self):
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=['is_read', 'read_at'])


class MessageAttachment(models.Model):
    ALLOWED_TYPES = ['image/jpeg', 'image/png', 'image/webp', 'image/gif']

    message  = models.ForeignKey(
        Message,
        on_delete=models.CASCADE,
        related_name='attachments',
    )
    file     = models.ImageField(upload_to='messaging/attachments/%Y/%m/')
    filename = models.CharField(max_length=255)
    filesize = models.PositiveIntegerField(help_text='Size in bytes')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'Attachment({self.filename}) on message {self.message_id}'
