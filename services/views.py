from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import ServiceRequest, ServiceReview
from .serializers import ServiceRequestSerializer, ServiceReviewSerializer


class ServiceRequestListCreateView(generics.ListCreateAPIView):
    serializer_class = ServiceRequestSerializer

    def get_queryset(self):
        return ServiceRequest.objects.filter(requester=self.request.user)


class ServiceRequestDetailView(generics.RetrieveUpdateAPIView):
    serializer_class = ServiceRequestSerializer

    def get_queryset(self):
        return ServiceRequest.objects.filter(requester=self.request.user)


class AvailableServicesView(generics.ListAPIView):
    serializer_class = ServiceRequestSerializer

    def get_queryset(self):
        user = self.request.user
        return ServiceRequest.objects.filter(
            status='pending', country_code=user.current_country,
        ).exclude(requester=user)


class AcceptServiceView(APIView):
    def post(self, request, pk):
        try:
            sr = ServiceRequest.objects.get(pk=pk, status='pending')
        except ServiceRequest.DoesNotExist:
            return Response({'detail': 'Service not found.'}, status=404)
        if sr.requester == request.user:
            return Response({'detail': 'Cannot accept your own request.'}, status=400)
        sr.provider = request.user
        sr.status   = 'accepted'
        sr.save()
        return Response(ServiceRequestSerializer(sr, context={'request': request}).data)


class ReviewServiceView(generics.CreateAPIView):
    serializer_class = ServiceReviewSerializer

    def perform_create(self, serializer):
        sr = ServiceRequest.objects.get(
            pk=self.kwargs['pk'], requester=self.request.user, status='completed'
        )
        serializer.save(service_request=sr, reviewer=self.request.user) 
