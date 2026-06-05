# admin.py (add to your existing admin.py file)
from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.urls import reverse
from django.utils import timezone
from django.db.models import Count, Q, F
from django.contrib.admin import SimpleListFilter
from . import models


class CommunityVisibilityFilter(SimpleListFilter):
    """Filter communities by visibility"""
    title = 'Visibility'
    parameter_name = 'visibility'
    
    def lookups(self, request, model_admin):
        return [
            ('public', 'Public'),
            ('private', 'Private'),
        ]
    
    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(visibility=self.value())
        return queryset


class PostTypeFilter(SimpleListFilter):
    """Filter posts by type"""
    title = 'Post Type'
    parameter_name = 'post_type'
    
    def lookups(self, request, model_admin):
        return models.Post.POST_TYPES
    
    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(post_type=self.value())
        return queryset


class PostModerationFilter(SimpleListFilter):
    """Filter posts by moderation status"""
    title = 'Moderation Status'
    parameter_name = 'moderation'
    
    def lookups(self, request, model_admin):
        return [
            ('approved', 'Approved'),
            ('flagged', 'Flagged'),
            ('deleted', 'Deleted'),
            ('pending_review', 'Pending Review'),
        ]
    
    def queryset(self, request, queryset):
        if self.value() == 'approved':
            return queryset.filter(is_approved=True, is_flagged=False, is_deleted=False)
        if self.value() == 'flagged':
            return queryset.filter(is_flagged=True)
        if self.value() == 'deleted':
            return queryset.filter(is_deleted=True)
        if self.value() == 'pending_review':
            return queryset.filter(is_approved=False, is_flagged=False, is_deleted=False)
        return queryset


class CommunityMemberRoleFilter(SimpleListFilter):
    """Filter community members by role"""
    title = 'Role'
    parameter_name = 'role'
    
    def lookups(self, request, model_admin):
        return models.CommunityMember.ROLES
    
    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(role=self.value())
        return queryset


# Inline admins
class CommunityMemberInline(admin.TabularInline):
    model = models.CommunityMember
    extra = 0
    fields = ['user', 'role', 'is_banned', 'joined_at']
    readonly_fields = ['joined_at']
    raw_id_fields = ['user']
    show_change_link = True
    can_delete = True


class CommunityInviteInline(admin.TabularInline):
    model = models.CommunityInvite
    extra = 0
    fields = ['email', 'token', 'used', 'expires_at', 'created_at']
    readonly_fields = ['token', 'created_at']
    show_change_link = True


class PostImageInline(admin.TabularInline):
    model = models.PostImage
    extra = 1
    fields = ['image_preview', 'image', 'caption', 'order']
    readonly_fields = ['image_preview']
    
    def image_preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" width="80" style="object-fit: cover; border-radius: 4px;" />', obj.image.url)
        return "-"
    image_preview.short_description = 'Preview'


class CommentInline(admin.TabularInline):
    model = models.Comment
    extra = 0
    fields = ['author', 'content_short', 'created_at']
    readonly_fields = ['author', 'created_at']
    raw_id_fields = ['author']
    can_delete = True
    
    def content_short(self, obj):
        return obj.content[:100] + '...' if len(obj.content) > 100 else obj.content
    content_short.short_description = 'Comment'


class PostLikeInline(admin.TabularInline):
    model = models.PostLike
    extra = 0
    fields = ['user', 'created_at']
    readonly_fields = ['created_at']
    raw_id_fields = ['user']


@admin.register(models.Community)
class CommunityAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'creator_link', 'country_code', 'visibility_badge', 
        'member_count', 'post_count', 'is_active', 'created_at'
    ]
    list_filter = [CommunityVisibilityFilter, 'is_active', 'country_code', 'created_at']
    search_fields = ['name', 'slug', 'description', 'creator__email', 'creator__username']
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ['id', 'member_count', 'post_count', 'created_at', 'updated_at']
    list_per_page = 25
    list_editable = ['is_active']
    raw_id_fields = ['creator']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'slug', 'description', 'visibility', 'country_code')
        }),
        ('Moderation', {
            'fields': ('is_active', 'purpose', 'rules')
        }),
        ('Media', {
            'fields': ('cover_image',)
        }),
        ('Statistics', {
            'fields': ('member_count', 'post_count'),
            'classes': ('collapse',)
        }),
        ('System Fields', {
            'fields': ('id', 'creator', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    inlines = [CommunityMemberInline, CommunityInviteInline]
    
    def creator_link(self, obj):
        url = reverse('admin:users_user_change', args=[obj.creator.id])
        return format_html('<a href="{}">{}</a>', url, obj.creator.get_full_name() or obj.creator.username)
    creator_link.short_description = 'Creator'
    
    def visibility_badge(self, obj):
        if obj.visibility == 'public':
            return mark_safe('<span style="color: #27ae60;">🌍 Public</span>')
        return mark_safe('<span style="color: #e74c3c;">🔒 Private</span>')
    visibility_badge.short_description = 'Visibility'
    
    actions = ['activate_communities', 'deactivate_communities', 'reset_stats']
    
    def activate_communities(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f'{updated} communities activated.')
    activate_communities.short_description = 'Activate selected communities'
    
    def deactivate_communities(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} communities deactivated.')
    deactivate_communities.short_description = 'Deactivate selected communities'
    
    def reset_stats(self, request, queryset):
        for community in queryset:
            community.member_count = community.members.filter(is_banned=False).count()
            community.post_count = community.posts.filter(is_deleted=False).count()
            community.save()
        self.message_user(request, f'Stats reset for {queryset.count()} communities.')
    reset_stats.short_description = 'Recalculate member/post counts'


@admin.register(models.CommunityMember)
class CommunityMemberAdmin(admin.ModelAdmin):
    list_display = [
        'community_link', 'user_link', 'role', 'is_banned',
        'joined_at', 'days_as_member'
    ]
    list_filter = [CommunityMemberRoleFilter, 'is_banned', 'joined_at']
    search_fields = ['community__name', 'user__email', 'user__username']
    raw_id_fields = ['community', 'user']
    readonly_fields = ['id', 'joined_at', 'banned_at']
    list_per_page = 30
    list_editable = ['role', 'is_banned']
    
    fieldsets = (
        ('Membership Details', {
            'fields': ('community', 'user', 'role')
        }),
        ('Ban Status', {
            'fields': ('is_banned', 'banned_at', 'ban_reason')
        }),
        ('System Fields', {
            'fields': ('id', 'joined_at'),
            'classes': ('collapse',)
        }),
    )
    
    def community_link(self, obj):
        url = reverse('admin:community_community_change', args=[obj.community.id])
        return format_html('<a href="{}">{}</a>', url, obj.community.name)
    community_link.short_description = 'Community'
    
    def user_link(self, obj):
        url = reverse('admin:users_user_change', args=[obj.user.id])
        return format_html('<a href="{}">{}</a>', url, obj.user.get_full_name() or obj.user.username)
    user_link.short_description = 'User'
    
    def role_badge(self, obj):
        colors = {
            'member': '#95a5a6',
            'moderator': '#3498db',
            'admin': '#e74c3c'
        }
        color = colors.get(obj.role, '#95a5a6')
        return format_html('<span style="color: {}; font-weight: bold;">{}</span>', color, obj.role.title())
    role_badge.short_description = 'Role'
    
    def days_as_member(self, obj):
        days = (timezone.now() - obj.joined_at).days
        return f"{days} days"
    days_as_member.short_description = 'Member for'
    
    actions = ['ban_members', 'unban_members', 'make_moderator', 'make_admin', 'make_member']
    
    def ban_members(self, request, queryset):
        now = timezone.now()
        updated = queryset.update(is_banned=True, banned_at=now)
        self.message_user(request, f'{updated} members banned.')
    ban_members.short_description = 'Ban selected members'
    
    def unban_members(self, request, queryset):
        updated = queryset.update(is_banned=False, banned_at=None, ban_reason='')
        self.message_user(request, f'{updated} members unbanned.')
    unban_members.short_description = 'Unban selected members'
    
    def make_moderator(self, request, queryset):
        updated = queryset.update(role='moderator')
        self.message_user(request, f'{updated} members promoted to moderator.')
    make_moderator.short_description = 'Make Moderator'
    
    def make_admin(self, request, queryset):
        updated = queryset.update(role='admin')
        self.message_user(request, f'{updated} members promoted to admin.')
    make_admin.short_description = 'Make Admin'
    
    def make_member(self, request, queryset):
        updated = queryset.update(role='member')
        self.message_user(request, f'{updated} members demoted to member.')
    make_member.short_description = 'Make Member'


@admin.register(models.CommunityInvite)
class CommunityInviteAdmin(admin.ModelAdmin):
    list_display = [
        'community_link', 'invited_by_link', 'email', 'token_short', 
        'used_badge', 'expires_at_display', 'created_at'
    ]
    list_filter = ['used', 'created_at', 'expires_at']
    search_fields = ['email', 'token', 'community__name', 'invited_by__email']
    raw_id_fields = ['community', 'invited_by']
    readonly_fields = ['id', 'token', 'created_at', 'used_at']
    list_per_page = 30
    
    fieldsets = (
        ('Invitation Details', {
            'fields': ('community', 'invited_by', 'email', 'token')
        }),
        ('Status', {
            'fields': ('used', 'used_at', 'expires_at')
        }),
        ('System Fields', {
            'fields': ('id', 'created_at'),
            'classes': ('collapse',)
        }),
    )
    
    def community_link(self, obj):
        url = reverse('admin:community_community_change', args=[obj.community.id])
        return format_html('<a href="{}">{}</a>', url, obj.community.name)
    community_link.short_description = 'Community'
    
    def invited_by_link(self, obj):
        url = reverse('admin:users_user_change', args=[obj.invited_by.id])
        return format_html('<a href="{}">{}</a>', url, obj.invited_by.get_full_name() or obj.invited_by.username)
    invited_by_link.short_description = 'Invited By'
    
    def token_short(self, obj):
        return obj.token[:12] + '...' if len(obj.token) > 12 else obj.token
    token_short.short_description = 'Token'
    
    def used_badge(self, obj):
        if obj.used:
            return mark_safe('<span style="color: #27ae60;">✓ Used</span>')
        elif obj.expires_at < timezone.now():
            return mark_safe('<span style="color: #e74c3c;">✗ Expired</span>')
        else:
            return mark_safe('<span style="color: #3498db;">⏳ Pending</span>')
    used_badge.short_description = 'Status'
    
    def expires_at_display(self, obj):
        if obj.expires_at < timezone.now():
            return format_html('<span style="color: #e74c3c;">{}</span>', obj.expires_at.strftime('%Y-%m-%d %H:%M'))
        return obj.expires_at.strftime('%Y-%m-%d %H:%M')
    expires_at_display.short_description = 'Expires'


@admin.register(models.Post)
class PostAdmin(admin.ModelAdmin):
    list_display = [
        'id_short', 'community_link', 'author_link', 'post_type_badge',
        'content_short', 'like_count', 'comment_count', 'is_approved', 'is_flagged', 'is_deleted', 'created_at'
    ]
    list_filter = [PostTypeFilter, PostModerationFilter, 'is_approved', 'is_flagged', 'is_deleted', 'created_at']
    search_fields = ['content', 'author__email', 'author__username', 'community__name']
    raw_id_fields = ['community', 'author', 'shop_listing', 'deleted_by']
    readonly_fields = ['id', 'like_count', 'comment_count', 'created_at', 'updated_at', 'flagged_at', 'deleted_at']
    list_per_page = 25
    list_editable = ['is_approved', 'is_flagged', 'is_deleted']

    fieldsets = (
        ('Post Information', {
            'fields': ('community', 'author', 'post_type', 'content')
        }),
        ('Media & Promotion', {
            'fields': ('video_url', 'video_title', 'video_thumbnail', 'shop_listing')
        }),
        ('Moderation', {
            'fields': ('is_approved', 'is_flagged', 'flagged_at', 'is_deleted', 'deleted_at', 'deleted_by')
        }),
        ('Statistics', {
            'fields': ('like_count', 'comment_count'),
            'classes': ('collapse',)
        }),
        ('System Fields', {
            'fields': ('id', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    inlines = [PostImageInline, CommentInline, PostLikeInline]
    
    def id_short(self, obj):
        return format_html('<code>{}</code>', obj.id[:8])
    id_short.short_description = 'ID'
    
    def community_link(self, obj):
        url = reverse('admin:community_community_change', args=[obj.community.id])
        return format_html('<a href="{}">{}</a>', url, obj.community.name)
    community_link.short_description = 'Community'
    
    def author_link(self, obj):
        url = reverse('admin:users_user_change', args=[obj.author.id])
        return format_html('<a href="{}">{}</a>', url, obj.author.get_full_name() or obj.author.username)
    author_link.short_description = 'Author'
    
    def post_type_badge(self, obj):
        icons = {
            'text': '📝',
            'image': '🖼️',
            'video_link': '🎥',
            'shop_promo': '🏪',
            'event': '📅'
        }
        icon = icons.get(obj.post_type, '📄')
        return format_html('{} {}', icon, obj.get_post_type_display())
    post_type_badge.short_description = 'Type'
    
    def content_short(self, obj):
        return obj.content[:100] + '...' if len(obj.content) > 100 else obj.content
    content_short.short_description = 'Content'
    
    def moderation_badge(self, obj):
        if obj.is_deleted:
            return mark_safe('<span style="color: #e74c3c;">🗑️ Deleted</span>')
        elif obj.is_flagged:
            return mark_safe('<span style="color: #f39c12;">⚠️ Flagged</span>')
        elif not obj.is_approved:
            return mark_safe('<span style="color: #e67e22;">⏳ Pending</span>')
        else:
            return mark_safe('<span style="color: #27ae60;">✓ Approved</span>')
    moderation_badge.short_description = 'Status'
    
    actions = ['approve_posts', 'flag_posts', 'delete_posts', 'restore_posts']
    
    def approve_posts(self, request, queryset):
        updated = queryset.update(is_approved=True, is_flagged=False)
        self.message_user(request, f'{updated} posts approved.')
    approve_posts.short_description = 'Approve selected posts'
    
    def flag_posts(self, request, queryset):
        now = timezone.now()
        updated = queryset.update(is_flagged=True, flagged_at=now, is_approved=False)
        self.message_user(request, f'{updated} posts flagged for review.')
    flag_posts.short_description = 'Flag selected posts'
    
    def delete_posts(self, request, queryset):
        now = timezone.now()
        updated = queryset.update(is_deleted=True, deleted_at=now, deleted_by=request.user)
        self.message_user(request, f'{updated} posts soft-deleted.')
    delete_posts.short_description = 'Soft delete selected posts'
    
    def restore_posts(self, request, queryset):
        updated = queryset.update(is_deleted=False, deleted_at=None, deleted_by=None)
        self.message_user(request, f'{updated} posts restored.')
    restore_posts.short_description = 'Restore selected posts'


@admin.register(models.PostImage)
class PostImageAdmin(admin.ModelAdmin):
    list_display = ['id', 'post_link', 'image_preview', 'caption', 'order']
    list_filter = ['order']
    search_fields = ['post__content', 'caption']
    raw_id_fields = ['post']
    readonly_fields = ['id', 'image_preview']
    list_editable = ['caption', 'order']
    list_per_page = 50

    def post_link(self, obj):
        url = reverse('admin:community_post_change', args=[obj.post.id])
        return format_html('<a href="{}">Post #{}</a>', url, obj.post.id[:8])
    post_link.short_description = 'Post'

    def image_preview(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" width="80" style="object-fit: cover; border-radius: 4px;" />',
                obj.image.url,
            )
        return '-'
    image_preview.short_description = 'Preview'


@admin.register(models.Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = [
        'id_short', 'post_link', 'author_link', 'content_short', 
        'parent_info', 'is_deleted', 'created_at'
    ]
    list_filter = ['is_deleted', 'created_at']
    search_fields = ['content', 'author__email', 'author__username', 'post__content']
    raw_id_fields = ['post', 'author', 'parent']
    readonly_fields = ['id', 'created_at', 'updated_at']
    list_per_page = 30
    
    fieldsets = (
        ('Comment Details', {
            'fields': ('post', 'author', 'parent', 'content')
        }),
        ('Status', {
            'fields': ('is_deleted',)
        }),
        ('System Fields', {
            'fields': ('id', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def id_short(self, obj):
        return format_html('<code>{}</code>', obj.id[:8])
    id_short.short_description = 'ID'
    
    def post_link(self, obj):
        url = reverse('admin:community_post_change', args=[obj.post.id])
        return format_html('<a href="{}">Post</a>', url)
    post_link.short_description = 'Post'
    
    def author_link(self, obj):
        url = reverse('admin:users_user_change', args=[obj.author.id])
        return format_html('<a href="{}">{}</a>', url, obj.author.get_full_name() or obj.author.username)
    author_link.short_description = 'Author'
    
    def content_short(self, obj):
        return obj.content[:100] + '...' if len(obj.content) > 100 else obj.content
    content_short.short_description = 'Comment'
    
    def parent_info(self, obj):
        if obj.parent:
            return format_html('↳ Reply to #{}', obj.parent.id[:8])
        return '-'
    parent_info.short_description = 'Parent'
    
    actions = ['delete_comments', 'restore_comments']
    
    def delete_comments(self, request, queryset):
        updated = queryset.update(is_deleted=True)
        self.message_user(request, f'{updated} comments deleted.')
    delete_comments.short_description = 'Delete selected comments'
    
    def restore_comments(self, request, queryset):
        updated = queryset.update(is_deleted=False)
        self.message_user(request, f'{updated} comments restored.')
    restore_comments.short_description = 'Restore selected comments'


@admin.register(models.PostLike)
class PostLikeAdmin(admin.ModelAdmin):
    list_display = ['post_link', 'user_link', 'created_at']
    list_filter = ['created_at']
    search_fields = ['post__content', 'user__email', 'user__username']
    raw_id_fields = ['post', 'user']
    readonly_fields = ['id', 'created_at']
    list_per_page = 50
    
    def post_link(self, obj):
        url = reverse('admin:community_post_change', args=[obj.post.id])
        return format_html('<a href="{}">Post #{}</a>', url, obj.post.id[:8])
    post_link.short_description = 'Post'
    
    def user_link(self, obj):
        url = reverse('admin:users_user_change', args=[obj.user.id])
        return format_html('<a href="{}">{}</a>', url, obj.user.get_full_name() or obj.user.username)
    user_link.short_description = 'User'


@admin.register(models.PostReport)
class PostReportAdmin(admin.ModelAdmin):
    list_display = [
        'post_link', 'reporter_link', 'reason', 'detail_short',
        'resolved', 'created_at'
    ]
    list_filter = ['reason', 'resolved', 'created_at']
    search_fields = ['post__content', 'reporter__email', 'reporter__username', 'detail']
    raw_id_fields = ['post', 'reporter', 'resolved_by']
    readonly_fields = ['id', 'created_at', 'resolved_at']
    list_per_page = 30
    list_editable = ['resolved']
    
    fieldsets = (
        ('Report Details', {
            'fields': ('post', 'reporter', 'reason', 'detail')
        }),
        ('Resolution', {
            'fields': ('resolved', 'resolved_by', 'resolved_at')
        }),
        ('System Fields', {
            'fields': ('id', 'created_at'),
            'classes': ('collapse',)
        }),
    )
    
    def post_link(self, obj):
        url = reverse('admin:community_post_change', args=[obj.post.id])
        return format_html('<a href="{}">Post #{}</a>', url, obj.post.id[:8])
    post_link.short_description = 'Post'
    
    def reporter_link(self, obj):
        url = reverse('admin:users_user_change', args=[obj.reporter.id])
        return format_html('<a href="{}">{}</a>', url, obj.reporter.get_full_name() or obj.reporter.username)
    reporter_link.short_description = 'Reporter'
    
    def reason_badge(self, obj):
        return format_html('<span style="background-color: #e74c3c; color: white; padding: 2px 6px; border-radius: 3px;">{}</span>', 
                          obj.get_reason_display())
    reason_badge.short_description = 'Reason'
    
    def detail_short(self, obj):
        return obj.detail[:50] + '...' if len(obj.detail) > 50 else obj.detail
    detail_short.short_description = 'Details'
    
    def resolved_badge(self, obj):
        if obj.resolved:
            return mark_safe('<span style="color: #27ae60;">✓ Resolved</span>')
        return mark_safe('<span style="color: #e74c3c;">⏳ Pending</span>')
    resolved_badge.short_description = 'Status'
    
    actions = ['mark_resolved', 'mark_pending', 'delete_post_and_resolve']
    
    def mark_resolved(self, request, queryset):
        now = timezone.now()
        updated = queryset.update(resolved=True, resolved_by=request.user, resolved_at=now)
        self.message_user(request, f'{updated} reports marked as resolved.')
    mark_resolved.short_description = 'Mark as resolved'
    
    def mark_pending(self, request, queryset):
        updated = queryset.update(resolved=False, resolved_by=None, resolved_at=None)
        self.message_user(request, f'{updated} reports marked as pending.')
    mark_pending.short_description = 'Mark as pending'
    
    def delete_post_and_resolve(self, request, queryset):
        for report in queryset:
            report.post.is_deleted = True
            report.post.deleted_at = timezone.now()
            report.post.deleted_by = request.user
            report.post.save()
            report.resolved = True
            report.resolved_by = request.user
            report.resolved_at = timezone.now()
            report.save()
        self.message_user(request, f'Posts deleted and {queryset.count()} reports resolved.')
    delete_post_and_resolve.short_description = 'Delete post & resolve report'


@admin.register(models.CommunityEvent)
class CommunityEventAdmin(admin.ModelAdmin):
    list_display = [
        'title', 'community_link', 'event_type_badge', 'location_short',
        'starts_at_display', 'ends_at_display', 'is_cancelled', 'created_by_link'
    ]
    list_filter = ['event_type', 'is_cancelled', 'starts_at']
    search_fields = ['title', 'description', 'location', 'community__name']
    raw_id_fields = ['community', 'created_by']
    readonly_fields = ['id', 'created_at']
    list_per_page = 25
    
    fieldsets = (
        ('Event Information', {
            'fields': ('community', 'created_by', 'title', 'description', 'event_type')
        }),
        ('Location & Time', {
            'fields': ('location', 'event_url', 'starts_at', 'ends_at')
        }),
        ('Media', {
            'fields': ('cover_image',)
        }),
        ('Status', {
            'fields': ('is_cancelled',)
        }),
        ('System Fields', {
            'fields': ('id', 'created_at'),
            'classes': ('collapse',)
        }),
    )
    
    def community_link(self, obj):
        url = reverse('admin:community_community_change', args=[obj.community.id])
        return format_html('<a href="{}">{}</a>', url, obj.community.name)
    community_link.short_description = 'Community'
    
    def event_type_badge(self, obj):
        icons = {'meetup': '👥', 'webinar': '💻', 'hangout': '🍻', 'other': '📌'}
        icon = icons.get(obj.event_type, '📅')
        return format_html('{} {}', icon, obj.get_event_type_display())
    event_type_badge.short_description = 'Type'
    
    def location_short(self, obj):
        return obj.location[:50] + '...' if len(obj.location) > 50 else obj.location
    location_short.short_description = 'Location'
    
    def starts_at_display(self, obj):
        if obj.starts_at > timezone.now():
            return format_html('<span style="color: #27ae60;">📅 {}</span>', obj.starts_at.strftime('%Y-%m-%d %H:%M'))
        return obj.starts_at.strftime('%Y-%m-%d %H:%M')
    starts_at_display.short_description = 'Starts'
    
    def ends_at_display(self, obj):
        return obj.ends_at.strftime('%Y-%m-%d %H:%M') if obj.ends_at else '-'
    ends_at_display.short_description = 'Ends'
    
    def created_by_link(self, obj):
        url = reverse('admin:users_user_change', args=[obj.created_by.id])
        return format_html('<a href="{}">{}</a>', url, obj.created_by.get_full_name() or obj.created_by.username)
    created_by_link.short_description = 'Created By'
    
    actions = ['cancel_events', 'uncancel_events']
    
    def cancel_events(self, request, queryset):
        updated = queryset.update(is_cancelled=True)
        self.message_user(request, f'{updated} events cancelled.')
    cancel_events.short_description = 'Cancel selected events'
    
    def uncancel_events(self, request, queryset):
        updated = queryset.update(is_cancelled=False)
        self.message_user(request, f'{updated} events restored.')
    uncancel_events.short_description = 'Uncancel selected events'


@admin.register(models.Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = [
        'id_short', 'community_link', 'sender_link', 'content_short',
        'reply_to_info', 'has_attachment', 'created_at'
    ]
    list_filter = ['created_at', 'is_deleted']
    search_fields = ['content', 'sender__email', 'sender__username', 'community__name']
    raw_id_fields = ['community', 'sender', 'reply_to']
    readonly_fields = ['id', 'created_at']
    list_per_page = 30
    
    fieldsets = (
        ('Message Details', {
            'fields': ('community', 'sender', 'reply_to', 'content')
        }),
        ('Attachments', {
            'fields': ('attachment', 'attachment_name', 'attachment_type', 'attachment_size')
        }),
        ('Status', {
            'fields': ('is_deleted',)
        }),
        ('System Fields', {
            'fields': ('id', 'created_at'),
            'classes': ('collapse',)
        }),
    )
    
    def id_short(self, obj):
        return format_html('<code>{}</code>', obj.id[:8])
    id_short.short_description = 'ID'
    
    def community_link(self, obj):
        url = reverse('admin:community_community_change', args=[obj.community.id])
        return format_html('<a href="{}">{}</a>', url, obj.community.name)
    community_link.short_description = 'Community'
    
    def sender_link(self, obj):
        url = reverse('admin:users_user_change', args=[obj.sender.id])
        return format_html('<a href="{}">{}</a>', url, obj.sender.get_full_name() or obj.sender.username)
    sender_link.short_description = 'Sender'
    
    def content_short(self, obj):
        return obj.content[:100] + '...' if len(obj.content) > 100 else obj.content
    content_short.short_description = 'Message'
    
    def reply_to_info(self, obj):
        if obj.reply_to:
            return format_html('↳ Reply to #{}', obj.reply_to.id[:8])
        return '-'
    reply_to_info.short_description = 'Reply To'
    
    def has_attachment(self, obj):
        return bool(obj.attachment)
    has_attachment.boolean = True
    has_attachment.short_description = 'Has Attachment'
    
    actions = ['delete_messages', 'restore_messages']
    
    def delete_messages(self, request, queryset):
        updated = queryset.update(is_deleted=True)
        self.message_user(request, f'{updated} messages deleted.')
    delete_messages.short_description = 'Delete selected messages'
    
    def restore_messages(self, request, queryset):
        updated = queryset.update(is_deleted=False)
        self.message_user(request, f'{updated} messages restored.')
    restore_messages.short_description = 'Restore selected messages'