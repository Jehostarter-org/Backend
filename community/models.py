import ulid
from django.db import models
from django.conf import settings


def generate_ulid():
    return str(ulid.new())


class Community(models.Model):
    """
    Gold members can create and join communities.
    e.g. "Nigerians in Brisbane", "Students in Canada", "UK Job Seekers"
    """
    id = models.CharField(primary_key=True, max_length=26, default=generate_ulid, editable=False)

    VISIBILITY = [('public', 'Public'), ('private', 'Private')]

    name         = models.CharField(max_length=200)
    slug         = models.SlugField(unique=True, max_length=220)
    description  = models.TextField()
    creator      = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='created_communities')
    country_code = models.CharField(max_length=2, blank=True)
    visibility   = models.CharField(max_length=10, choices=VISIBILITY, default='public')
    cover_image  = models.ImageField(upload_to='community_covers/', null=True, blank=True)
    is_active    = models.BooleanField(default=True)
    purpose      = models.TextField(blank=True)
    rules        = models.TextField(blank=True)
    member_count = models.PositiveIntegerField(default=0)
    post_count   = models.PositiveIntegerField(default=0)
    created_at   = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'communities'
        verbose_name_plural = 'Communities'
        ordering = ['-created_at']

    def __str__(self):
        return self.name


class CommunityMember(models.Model):
    """Who belongs to which community and their role."""
    id = models.CharField(primary_key=True, max_length=26, default=generate_ulid, editable=False)

    ROLES = [
        ('member',    'Member'),
        ('moderator', 'Moderator'),
        ('admin',     'Admin'),
    ]

    community  = models.ForeignKey(Community, on_delete=models.CASCADE, related_name='members')
    user       = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='community_memberships')
    role       = models.CharField(max_length=15, choices=ROLES, default='member')
    is_banned  = models.BooleanField(default=False)
    banned_at  = models.DateTimeField(null=True, blank=True)
    ban_reason = models.TextField(blank=True)
    joined_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'community_members'
        unique_together = ('community', 'user')

    def __str__(self):
        return f"{self.user} in {self.community} ({self.role})"


class CommunityInvite(models.Model):
    """Invite links to join a private community."""
    id         = models.CharField(primary_key=True, max_length=26, default=generate_ulid, editable=False)
    community  = models.ForeignKey(Community, on_delete=models.CASCADE, related_name='invites')
    invited_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='sent_invites')
    email      = models.EmailField(blank=True)
    token      = models.CharField(max_length=64, unique=True)
    used       = models.BooleanField(default=False)
    used_at    = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'community_invites'


class Post(models.Model):
    """
    Post inside a community.
    Text, image, YouTube video (watch without leaving app), or shop promotion.
    """
    id = models.CharField(primary_key=True, max_length=26, default=generate_ulid, editable=False)

    POST_TYPES = [
        ('text',       'Text'),
        ('image',      'Image'),
        ('video_link', 'YouTube Video'),
        ('shop_promo', 'Shop Promotion'),
        ('event',      'Event'),
    ]

    community       = models.ForeignKey(Community, on_delete=models.CASCADE, related_name='posts')
    author          = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='posts')
    post_type       = models.CharField(max_length=15, choices=POST_TYPES, default='text')
    content         = models.TextField()
    video_url       = models.URLField(blank=True)
    video_title     = models.CharField(max_length=300, blank=True)
    video_thumbnail = models.URLField(blank=True)
    shop_listing    = models.ForeignKey(
        'shops.ShopListing', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='community_promotions'
    )

    # Moderation
    is_approved = models.BooleanField(default=True)
    is_flagged  = models.BooleanField(default=False)
    flagged_at  = models.DateTimeField(null=True, blank=True)
    is_deleted  = models.BooleanField(default=False)
    deleted_at  = models.DateTimeField(null=True, blank=True)
    deleted_by  = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='deleted_posts'
    )

    like_count    = models.PositiveIntegerField(default=0)
    comment_count = models.PositiveIntegerField(default=0)
    created_at    = models.DateTimeField(auto_now_add=True)
    updated_at    = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'community_posts'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.post_type} by {self.author} in {self.community}"


class PostImage(models.Model):
    """Multiple images per post."""
    id      = models.CharField(primary_key=True, max_length=26, default=generate_ulid, editable=False)
    post    = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='images')
    image   = models.ImageField(upload_to='post_images/')
    caption = models.CharField(max_length=300, blank=True)
    order   = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = 'post_images'
        ordering = ['order']


class Comment(models.Model):
    """Threaded comments on posts."""
    id         = models.CharField(primary_key=True, max_length=26, default=generate_ulid, editable=False)
    post       = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='comments')
    author     = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='comments')
    parent     = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='replies')
    content    = models.TextField()
    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'post_comments'
        ordering = ['created_at']

    def __str__(self):
        return f"Comment by {self.author} on {self.post}"


class PostLike(models.Model):
    """Tracks who liked which post."""
    id         = models.CharField(primary_key=True, max_length=26, default=generate_ulid, editable=False)
    post       = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='likes')
    user       = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='liked_posts')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'post_likes'
        unique_together = ('post', 'user')


class PostReport(models.Model):
    """Report posts that violate community rules. Reviewed by admins/moderators."""
    id = models.CharField(primary_key=True, max_length=26, default=generate_ulid, editable=False)

    REASONS = [
        ('nudity',      'Nudity / Adult Content'),
        ('hate_speech', 'Hate Speech'),
        ('fraud',       'Fraud / Scam'),
        ('misleading',  'Misleading Information'),
        ('spam',        'Spam'),
        ('harassment',  'Harassment'),
        ('other',       'Other'),
    ]

    post        = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='reports')
    reporter    = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='post_reports')
    reason      = models.CharField(max_length=20, choices=REASONS)
    detail      = models.TextField(blank=True)
    resolved    = models.BooleanField(default=False)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='resolved_reports'
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'post_reports'

    def __str__(self):
        return f"Report – {self.reason} on {self.post}"


class CommunityEvent(models.Model):
    """Events created by community admins: meetups, webinars, hangouts."""
    id = models.CharField(primary_key=True, max_length=26, default=generate_ulid, editable=False)

    EVENT_TYPES = [
        ('meetup',  'Meetup'),
        ('webinar', 'Webinar'),
        ('hangout', 'Local Hangout'),
        ('other',   'Other'),
    ]

    community    = models.ForeignKey(Community, on_delete=models.CASCADE, related_name='events')
    created_by   = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='created_events')
    title        = models.CharField(max_length=300)
    description  = models.TextField()
    event_type   = models.CharField(max_length=15, choices=EVENT_TYPES, default='meetup')
    location     = models.CharField(max_length=300, blank=True)
    event_url    = models.URLField(blank=True)
    starts_at    = models.DateTimeField()
    ends_at      = models.DateTimeField(null=True, blank=True)
    cover_image  = models.ImageField(upload_to='event_covers/', null=True, blank=True)
    is_cancelled = models.BooleanField(default=False)
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'community_events'
        ordering = ['starts_at']

    def __str__(self):
        return f"{self.title} in {self.community}"