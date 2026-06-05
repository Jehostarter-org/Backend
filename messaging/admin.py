from django.contrib import admin
from .models import Conversation, Message, MessageAttachment


class MessageInline(admin.TabularInline):
    model          = Message
    extra          = 0
    readonly_fields = ['sender', 'body', 'service_card', 'is_read', 'created_at']
    can_delete     = False


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display   = ['id', 'participant_names', 'service_type', 'currency_code', 'location_country', 'updated_at']
    list_filter    = ['service_type', 'currency_code', 'location_country']
    search_fields  = ['participants__email', 'participants__first_name']
    readonly_fields = ['created_at', 'updated_at']
    inlines        = [MessageInline]

    def participant_names(self, obj):
        return ' · '.join(
            p.get_full_name() or p.email
            for p in obj.participants.all()
        )
    participant_names.short_description = 'Participants'


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display  = ['id', 'sender', 'conversation', 'body_preview', 'is_read', 'created_at']
    list_filter   = ['is_read']
    search_fields = ['sender__email', 'body']
    readonly_fields = ['created_at', 'read_at']

    def body_preview(self, obj):
        return obj.body[:60] or '[attachment]'
    body_preview.short_description = 'Preview'


@admin.register(MessageAttachment)
class MessageAttachmentAdmin(admin.ModelAdmin):
    list_display  = ['id', 'message', 'filename', 'filesize', 'uploaded_at']
    readonly_fields = ['uploaded_at']
