from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.urls import reverse
from .models import Conversation, Message, MessageAttachment


class MessageInline(admin.TabularInline):
    model          = Message
    extra          = 0
    readonly_fields = ['sender', 'body', 'reply_to', 'service_card', 'is_read', 'created_at']
    can_delete     = False

    def reply_to(self, obj):
        if obj.reply_to:
            return f'Reply to: {obj.reply_to.body[:30]}...'
        return '—'
    reply_to.short_description = 'Reply To'

    def service_card(self, obj):
        if obj.service_card:
            title = obj.service_card.get('title', '')
            return f'📋 {title}' if title else '📋 Card'
        return '—'
    service_card.short_description = 'Service Card'


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display   = ['id', 'participant_names', 'service_type', 'linked_object_id', 'currency_code', 'location_country', 'updated_at']
    list_filter    = ['service_type', 'currency_code', 'location_country']
    search_fields  = ['participants__email', 'participants__first_name', 'linked_object_id']
    readonly_fields = ['id', 'created_at', 'updated_at']
    inlines        = [MessageInline]
    list_per_page = 25

    fieldsets = (
        ('Participants', {
            'fields': ('id',)
        }),
        ('Service Context', {
            'fields': (
                'service_type', 'linked_object_type', 'linked_object_id',
                'currency_code', 'location_country',
            ),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def participant_names(self, obj):
        return ' · '.join(
            p.get_full_name() or p.email
            for p in obj.participants.all()
        )
    participant_names.short_description = 'Participants'


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display  = ['id', 'sender', 'conversation', 'body_preview', 'reply_to_display', 'has_service_card', 'is_read', 'created_at']
    list_filter   = ['is_read']
    search_fields = ['sender__email', 'body']
    readonly_fields = ['id', 'conversation', 'sender', 'body', 'is_read', 'created_at', 'read_at']
    raw_id_fields = ['conversation', 'sender', 'reply_to']

    fieldsets = (
        ('Message Info', {
            'fields': ('id', 'conversation', 'sender', 'body')
        }),
        ('Threading', {
            'fields': ('reply_to',),
            'classes': ('collapse',)
        }),
        ('Service Card', {
            'fields': ('service_card',),
            'classes': ('collapse',)
        }),
        ('Read Status', {
            'fields': ('is_read', 'read_at')
        }),
        ('Timestamps', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )

    def body_preview(self, obj):
        return obj.body[:60] or '[attachment]'
    body_preview.short_description = 'Preview'

    def reply_to_display(self, obj):
        if obj.reply_to:
            return format_html('↳ #{}: {}', obj.reply_to.id[:8], obj.reply_to.body[:30])
        return '—'
    reply_to_display.short_description = 'Reply To'

    def has_service_card(self, obj):
        return bool(obj.service_card)
    has_service_card.boolean = True
    has_service_card.short_description = 'Service Card'


@admin.register(MessageAttachment)
class MessageAttachmentAdmin(admin.ModelAdmin):
    list_display  = ['id', 'message', 'filename', 'filesize', 'uploaded_at']
    readonly_fields = ['id', 'uploaded_at']
