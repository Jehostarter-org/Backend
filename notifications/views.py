from rest_framework import generics, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from django.utils import timezone
from .models import Notification
from .serializers import NotificationSerializer


class NotificationListView(generics.ListAPIView):
    serializer_class = NotificationSerializer

    def get_queryset(self):
        qs = self.request.user.notifications.all()
        if self.request.query_params.get('unread'):
            qs = qs.filter(is_read=False)
        return qs


class MarkNotificationReadView(APIView):
    def post(self, request, pk):
        updated = request.user.notifications.filter(pk=pk).update(is_read=True, read_at=timezone.now())
        if not updated:
            return Response({'detail': 'Not found.'}, status=404)
        return Response({'detail': 'Marked as read.'})


class MarkAllReadView(APIView):
    def post(self, request):
        request.user.notifications.filter(is_read=False).update(is_read=True, read_at=timezone.now())
        return Response({'detail': 'All notifications marked as read.'})


class UnreadCountView(APIView):
    def get(self, request):
        count = request.user.notifications.filter(is_read=False).count()
        return Response({'unread_count': count}) 
