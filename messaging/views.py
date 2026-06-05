from django.contrib.auth import get_user_model
from django.conf import settings
from django.db.models import Q
from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Conversation, Message
from .serializers import (
    ConversationSerializer,
    MessageSerializer,
    MessageCreateSerializer,
    StartConversationSerializer,
)

User = get_user_model()


class InboxView(generics.ListAPIView):
    """
    GET /api/messaging/inbox/
    Returns all conversations for the authenticated user,
    sorted by most recent message.
    """
    serializer_class   = ConversationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            Conversation.objects
            .filter(participants=self.request.user)
            .prefetch_related('participants', 'messages')
            .order_by('-updated_at')
        )


class StartConversationView(generics.GenericAPIView):
    """
    POST /api/messaging/start/
    Opens a DM thread (or returns existing one) between the current user
    and a recipient. Accepts optional service card context so the first
    message carries the service card automatically.

    Frontend calls this when user taps 'Message' on any profile/shop/service.
    """
    serializer_class   = StartConversationSerializer
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        me = request.user
        recipient_id = data.get('recipient_id')

        if not recipient_id and data.get('linked_object_type') == 'shop_listing':
            from shops.models import ShopListing

            listing = generics.get_object_or_404(
                ShopListing.objects.select_related('shop__owner'),
                pk=data.get('linked_object_id'),
                is_deleted=False,
            )
            recipient_id = listing.shop.owner_id

        recipient = User.objects.get(pk=recipient_id)

        if recipient.pk == me.pk:
            return Response(
                {'recipient_id': ['You cannot message yourself.']},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Find existing conversation between these two users
        existing = (
            Conversation.objects
            .filter(participants=me)
            .filter(participants=recipient)
        )
        if data.get('service_type'):
            existing = existing.filter(service_type=data['service_type'])
            if data.get('linked_object_id'):
                existing = existing.filter(linked_object_id=data['linked_object_id'])

        conversation = existing.first()

        if not conversation:
            # Resolve currency from sender's country
            country  = getattr(me, 'country', None) or ''
            currency = settings.COUNTRY_CURRENCY_MAP.get(country, '')

            conversation = Conversation.objects.create(
                service_type       = data.get('service_type'),
                linked_object_type = data.get('linked_object_type'),
                linked_object_id   = data.get('linked_object_id'),
                currency_code      = currency,
                location_country   = country,
            )
            conversation.participants.set([me, recipient])

        # Send initial message + service card if provided
        initial_body = data.get('initial_message', '').strip()
        service_card = data.get('service_card')

        if initial_body or service_card:
            Message.objects.create(
                conversation=conversation,
                sender=me,
                body=initial_body,
                service_card=service_card,
            )
            conversation.save()  # bumps updated_at

        out = ConversationSerializer(conversation, context={'request': request})
        return Response(out.data, status=status.HTTP_201_CREATED)


class ConversationDetailView(generics.RetrieveAPIView):
    """
    GET /api/messaging/conversations/<id>/
    Returns conversation metadata. Frontend uses this to render the chat header.
    """
    serializer_class   = ConversationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Conversation.objects.filter(participants=self.request.user)


class MessageListView(generics.ListAPIView):
    """
    GET /api/messaging/conversations/<conversation_id>/messages/
    Returns paginated messages for a conversation (oldest first).
    Also marks all unread messages in this thread as read.
    """
    serializer_class   = MessageSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        conversation_id = self.kwargs['conversation_id']
        user = self.request.user

        # Security: only participants can read this thread
        conversation = generics.get_object_or_404(
            Conversation,
            pk=conversation_id,
            participants=user,
        )

        # Mark all incoming messages as read
        conversation.messages.filter(
            is_read=False
        ).exclude(sender=user).update(
            is_read=True,
        )

        return conversation.messages.select_related('sender').prefetch_related('attachments')


class SendMessageView(generics.CreateAPIView):
    """
    POST /api/messaging/conversations/<conversation_id>/messages/
    Sends a new message. The WebSocket consumer also handles this
    for real-time delivery — this REST endpoint is the fallback.
    """
    serializer_class   = MessageCreateSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        message = serializer.save()
        # Bump conversation updated_at for inbox ordering
        message.conversation.save()

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        return ctx


class DeleteMessageView(generics.DestroyAPIView):
    """
    DELETE /api/messaging/conversations/<conversation_id>/messages/<message_id>/
    Deletes a message sent by the current user in this conversation.
    """
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return generics.get_object_or_404(
            Message,
            pk=self.kwargs['message_id'],
            conversation_id=self.kwargs['conversation_id'],
            conversation__participants=self.request.user,
            sender=self.request.user,
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def mark_read(request, conversation_id):
    """
    POST /api/messaging/conversations/<conversation_id>/read/
    Marks all messages in the thread as read for the current user.
    """
    conversation = generics.get_object_or_404(
        Conversation,
        pk=conversation_id,
        participants=request.user,
    )
    updated = conversation.messages.filter(
        is_read=False
    ).exclude(
        sender=request.user
    ).update(is_read=True)

    return Response({'marked_read': updated})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def unread_count(request):
    """
    GET /api/messaging/unread-count/
    Returns the total unread message count for the notification badge.
    """
    count = (
        Message.objects
        .filter(
            conversation__participants=request.user,
            is_read=False,
        )
        .exclude(sender=request.user)
        .count()
    )
    return Response({'unread_count': count})
