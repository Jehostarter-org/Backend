from django.contrib import admin
from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = [
        'title', 'recipient', 'notification_type', 'is_read',
        'actor_display', 'link_short', 'created_at',
    ]
    list_filter = ['notification_type', 'is_read', 'created_at']
    search_fields = ['title', 'message', 'recipient__email', 'recipient__username']
    raw_id_fields = ['recipient', 'actor']
    readonly_fields = ['id', 'created_at', 'read_at']
    list_per_page = 50
    list_editable = ['is_read']

    fieldsets = (
        ('Notification Info', {
            'fields': ('id', 'recipient', 'actor', 'notification_type', 'title', 'message')
        }),
        ('Status', {
            'fields': ('is_read', 'read_at', 'link')
        }),
        ('Timestamps', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )

    def actor_display(self, obj):
        if obj.actor:
            return obj.actor.get_full_name() or obj.actor.username
        return '—'
    actor_display.short_description = 'Actor'

    def link_short(self, obj):
        if obj.link:
            return obj.link[:40] + '...' if len(obj.link) > 40 else obj.link
        return '—'
    link_short.short_description = 'Link'

    actions = ['mark_read', 'mark_unread']

    def mark_read(self, request, queryset):
        from django.utils import timezone as tz
        now = tz.now()
        updated = queryset.filter(is_read=False).update(is_read=True, read_at=now)
        self.message_user(request, f'{updated} notification(s) marked as read.')
    mark_read.short_description = 'Mark selected as read'

    def mark_unread(self, request, queryset):
        updated = queryset.filter(is_read=True).update(is_read=False, read_at=None)
        self.message_user(request, f'{updated} notification(s) marked as unread.')
    mark_unread.short_description = 'Mark selected as unread'
