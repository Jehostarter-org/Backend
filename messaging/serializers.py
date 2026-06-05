from rest_framework import serializers
from django.contrib.auth import get_user_model

from .models import Conversation, Message, MessageAttachment

User = get_user_model()


class ParticipantSerializer(serializers.ModelSerializer):
    """Minimal user info shown inside conversation/message previews."""
    full_name    = serializers.SerializerMethodField()
    is_gold      = serializers.SerializerMethodField()
    avatar_url   = serializers.SerializerMethodField()

    class Meta:
        model  = User
        fields = ['id', 'full_name', 'email', 'is_gold', 'avatar_url']

    def get_full_name(self, obj):
        return obj.get_full_name() or obj.email

    def get_is_gold(self, obj):
        # Adjust to your actual membership field/relation name
        try:
            return obj.membership.plan == 'gold'
        except AttributeError:
            return False

    def get_avatar_url(self, obj):
        request = self.context.get('request')
        try:
            if obj.avatar and request:
                return request.build_absolute_uri(obj.avatar.url)
        except AttributeError:
            pass
        return None


class MessageAttachmentSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model  = MessageAttachment
        fields = ['id', 'url', 'filename', 'filesize', 'uploaded_at']

    def get_url(self, obj):
        request = self.context.get('request')
        if request:
            return request.build_absolute_uri(obj.file.url)
        return obj.file.url


class ReplyToPreviewSerializer(serializers.ModelSerializer):
    sender = ParticipantSerializer(read_only=True)

    class Meta:
        model = Message
        fields = ['id', 'sender', 'body', 'created_at']


class MessageSerializer(serializers.ModelSerializer):
    sender      = ParticipantSerializer(read_only=True)
    attachments = MessageAttachmentSerializer(many=True, read_only=True)
    reply_to    = ReplyToPreviewSerializer(read_only=True)

    class Meta:
        model  = Message
        fields = [
            'id', 'conversation', 'sender', 'reply_to', 'body',
            'is_read', 'read_at', 'service_card',
            'attachments', 'created_at',
        ]
        read_only_fields = [
            'id', 'sender', 'is_read', 'read_at',
            'service_card', 'attachments', 'created_at',
        ]


class MessageCreateSerializer(serializers.ModelSerializer):
    """Used when sending a new message via REST."""
    uploaded_images = serializers.ListField(
        child=serializers.ImageField(),
        required=False,
        write_only=True,
    )

    class Meta:
        model  = Message
        fields = ['conversation', 'reply_to', 'body', 'uploaded_images']

    def validate(self, attrs):
        body   = attrs.get('body', '').strip()
        images = attrs.get('uploaded_images', [])
        if not body and not images:
            raise serializers.ValidationError('Message must have text or an attachment.')
        reply_to = attrs.get('reply_to')
        conversation = attrs.get('conversation')
        if reply_to and conversation and reply_to.conversation_id != conversation.id:
            raise serializers.ValidationError('Reply message must belong to this conversation.')
        return attrs

    def validate_conversation(self, conversation):
        user = self.context['request'].user
        if not conversation.participants.filter(pk=user.pk).exists():
            raise serializers.ValidationError('You are not a participant in this conversation.')
        return conversation

    def create(self, validated_data):
        images = validated_data.pop('uploaded_images', [])
        message = Message.objects.create(
            sender=self.context['request'].user,
            **validated_data,
        )
        for img in images:
            MessageAttachment.objects.create(
                message=message,
                file=img,
                filename=img.name,
                filesize=img.size,
            )
        return message


class ConversationSerializer(serializers.ModelSerializer):
    """Full conversation detail with participants and latest message."""
    other_participant = serializers.SerializerMethodField()
    last_message      = serializers.SerializerMethodField()
    unread_count      = serializers.SerializerMethodField()

    class Meta:
        model  = Conversation
        fields = [
            'id', 'other_participant', 'last_message', 'unread_count',
            'service_type', 'linked_object_type', 'linked_object_id',
            'currency_code', 'location_country',
            'created_at', 'updated_at',
        ]

    def get_other_participant(self, obj):
        user = self.context['request'].user
        other = obj.get_other_participant(user)
        if other:
            return ParticipantSerializer(other, context=self.context).data
        return None

    def get_last_message(self, obj):
        msg = obj.messages.last()
        if msg:
            return {
                'id':         msg.id,
                'body':       msg.body[:80],
                'sender_id':  msg.sender_id,
                'created_at': msg.created_at,
            }
        return None

    def get_unread_count(self, obj):
        return obj.unread_count_for(self.context['request'].user)


class StartConversationSerializer(serializers.Serializer):
    """
    Payload to open a new DM thread.
    Called when user taps 'Message' on a profile, shop, or service.
    """
    recipient_id       = serializers.IntegerField(required=False, allow_null=True)
    initial_message    = serializers.CharField(required=False, allow_blank=True)

    # Service card context (optional — sent when opened from a service)
    service_type       = serializers.ChoiceField(
        choices=[
            'airport_pickup', 'home_inspection',
            'job_application', 'chaperon', 'migration_specialist',
        ],
        required=False,
        allow_null=True,
    )
    linked_object_type = serializers.CharField(required=False, allow_blank=True)
    linked_object_id   = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    service_card       = serializers.JSONField(required=False, allow_null=True)

    def validate_recipient_id(self, value):
        user = self.context['request'].user
        if value is None:
            return value
        if value == user.pk:
            raise serializers.ValidationError('You cannot message yourself.')
        if not User.objects.filter(pk=value).exists():
            raise serializers.ValidationError('Recipient not found.')
        return value

    def validate(self, attrs):
        if attrs.get('recipient_id'):
            return attrs

        if attrs.get('linked_object_type') == 'shop_listing' and attrs.get('linked_object_id'):
            return attrs

        raise serializers.ValidationError({
            'recipient_id': 'Recipient is required unless this conversation is linked to a shop listing.'
        })
