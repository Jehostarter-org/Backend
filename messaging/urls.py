from django.urls import path
from . import views

app_name = 'messaging'

urlpatterns = [
    # Inbox — list all conversations for current user
    path('inbox/', views.InboxView.as_view(), name='inbox'),

    # Unread badge count (for notification bell)
    path('unread-count/', views.unread_count, name='unread-count'),

    # Start or resume a conversation (called from profile/shop/service 'Message' button)
    path('start/', views.StartConversationView.as_view(), name='start'),

    # Conversation detail (header info)
    path('conversations/<int:pk>/', views.ConversationDetailView.as_view(), name='conversation-detail'),

    # Messages in a conversation (paginated)
    path('conversations/<int:conversation_id>/messages/', views.MessageListView.as_view(), name='message-list'),

    # Send a message via REST (WebSocket is primary; this is the fallback)
    path('conversations/<int:conversation_id>/messages/send/', views.SendMessageView.as_view(), name='message-send'),

    # Delete a message sent by the current user
    path('conversations/<int:conversation_id>/messages/<int:message_id>/', views.DeleteMessageView.as_view(), name='message-delete'),

    # Mark all messages in thread as read
    path('conversations/<int:conversation_id>/read/', views.mark_read, name='mark-read'),
]
