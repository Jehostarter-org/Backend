from django.urls import path
from .views import NotificationListView, MarkNotificationReadView, MarkAllReadView, UnreadCountView, DismissNotificationView

urlpatterns = [
    path('', NotificationListView.as_view(), name='notifications'),
    path('unread-count/', UnreadCountView.as_view(), name='unread_count'),
    path('mark-all-read/', MarkAllReadView.as_view(), name='mark_all_read'),
    path('<str:pk>/read/', MarkNotificationReadView.as_view(), name='mark_read'),
    path('<str:pk>/dismiss/', DismissNotificationView.as_view(), name='dismiss'),
]