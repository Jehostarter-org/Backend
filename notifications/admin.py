from django.contrib import admin
from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = [
        'title', 'recipient', 'notification_type', 'is_read', 'created_at',
    ]
    list_filter = ['notification_type', 'is_read', 'created_at']
    search_fields = ['title', 'message', 'recipient__email', 'recipient__username']
    raw_id_fields = ['recipient', 'actor']
    readonly_fields = ['id', 'created_at', 'read_at']
    list_per_page = 50
    list_editable = ['is_read']
