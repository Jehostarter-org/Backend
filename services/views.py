from rest_framework import generics, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from django.db import transaction
from django.utils import timezone
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from .models import (
    ServiceRequest, ServiceReview, AirportPickup,
    HomeInspection, ServiceProviderProfile,
    MigrationSpecialistApplication,
)
from .serializers import (
    ServiceRequestSerializer, ServiceReviewSerializer,
    ServiceProviderProfileSerializer,
    MigrationSpecialistApplicationSerializer,
)
from notifications.models import Notification

channel_layer = get_channel_layer()


def _broadcast(group, event_type, payload):
    async_to_sync(channel_layer.group_send)(
        group,
        {'type': event_type, 'payload': payload},
    )


# ── Service Requests ──────────────────────────────────────────────────────────

class ServiceRequestListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/services/        — list my own service requests
    POST /api/services/        — create a new service request
    """
    serializer_class = ServiceRequestSerializer

    def get_queryset(self):
        return ServiceRequest.objects.filter(
            requester=self.request.user
        ).select_related('provider').order_by('-created_at')


class ServiceRequestDetailView(generics.RetrieveUpdateAPIView):
    """
    GET   /api/services/<pk>/  — get details of a specific request
    PATCH /api/services/<pk>/  — update notes or scheduled_at (requester only)
    """
    serializer_class = ServiceRequestSerializer

    def get_queryset(self):
        return ServiceRequest.objects.filter(requester=self.request.user)


# ── Available Services Pool (Provider Dashboard) ──────────────────────────────

class AvailableServicesView(generics.ListAPIView):
    """
    GET /api/services/available/

    Shows pending service requests in the provider's city.
    Only shows requests matching the service types the provider is registered for.
    A Lagos driver only sees Lagos airport pickups — strict city-level filtering.
    """
    serializer_class = ServiceRequestSerializer

    def get_queryset(self):
        user = self.request.user

        # Get all service types this user is registered to provide
        provider_types = ServiceProviderProfile.objects.filter(
            user=user,
            is_active=True,
            city__iexact=user.city,
            country_code=user.current_country,
        ).values_list('service_type', flat=True)

        if not provider_types:
            return ServiceRequest.objects.none()

        return ServiceRequest.objects.filter(
            status='pending',
            service_type__in=provider_types,
            city__iexact=user.city,
            country_code=user.current_country,
        ).exclude(requester=user).select_related('requester')


class ClaimServiceView(APIView):
    """
    POST /api/services/<pk>/claim/

    First-come first-serve claiming with select_for_update to prevent
    two providers from claiming the same job simultaneously.
    Once claimed, broadcasts to remove it from all other providers' dashboards.
    """

    def post(self, request, pk):
        user = request.user

        try:
            with transaction.atomic():
                # Lock the row so no other request can claim it at the same time
                sr = ServiceRequest.objects.select_for_update().get(
                    pk=pk, status='pending'
                )

                if sr.requester == user:
                    return Response(
                        {'detail': 'You cannot claim your own request.'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                # Make sure the provider is actually registered for this service type
                is_registered = ServiceProviderProfile.objects.filter(
                    user=user,
                    service_type=sr.service_type,
                    city__iexact=sr.city,
                    country_code=sr.country_code,
                    is_active=True,
                ).exists()

                if not is_registered:
                    return Response(
                        {'detail': 'You are not registered to provide this service in this city.'},
                        status=status.HTTP_403_FORBIDDEN,
                    )

                sr.provider = user
                sr.status   = 'accepted'
                sr.save()

                # If it's an airport pickup, assign the driver too
                if sr.service_type == 'airport_pickup':
                    AirportPickup.objects.filter(service_request=sr).update(driver=user)

        except ServiceRequest.DoesNotExist:
            return Response(
                {'detail': 'This service is no longer available.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Notify the requester
        Notification.objects.create(
            recipient=sr.requester,
            actor=user,
            notification_type='service_accepted',
            title=f'Your {sr.get_service_type_display()} has been accepted',
            message=f'{user.get_full_name() or user.username} will handle your request.',
            link=f'/services/{sr.id}',
        )

        # Broadcast to requester's notification stream
        _broadcast(
            group=f'user_notifications_{sr.requester.id}',
            event_type='new_notification',
            payload={
                'type': 'service_accepted',
                'title': f'Your {sr.get_service_type_display()} has been accepted',
                'service_id': sr.id,
            }
        )

        # Broadcast to the available services pool so it disappears
        # from all other providers' dashboards instantly
        _broadcast(
            group=f'available_services_{sr.country_code}_{sr.city.lower()}_{sr.service_type}',
            event_type='service_claimed',
            payload={'service_id': sr.id},
        )

        return Response(
            ServiceRequestSerializer(sr, context={'request': request}).data,
            status=status.HTTP_200_OK,
        )


# ── My Provider Jobs ──────────────────────────────────────────────────────────

class MyProviderJobsView(generics.ListAPIView):
    """
    GET /api/services/my-jobs/
    Lists all service requests the current user is providing.
    """
    serializer_class = ServiceRequestSerializer

    def get_queryset(self):
        return ServiceRequest.objects.filter(
            provider=self.request.user
        ).select_related('requester').order_by('-created_at')


# ── Upcoming Airport Pickups Dashboard ───────────────────────────────────────

class UpcomingPickupsView(generics.ListAPIView):
    """
    GET /api/services/upcoming-pickups/

    For drivers — shows their upcoming claimed airport pickups
    sorted by arrival time, so the nearest one is always at the top.
    """
    serializer_class = ServiceRequestSerializer

    def get_queryset(self):
        return ServiceRequest.objects.filter(
            provider=self.request.user,
            service_type='airport_pickup',
            status__in=['accepted', 'in_progress'],
        ).select_related('requester', 'airport_pickup_details').order_by(
            'airport_pickup_details__arrival_datetime'
        )


# ── Inspection Report Upload ──────────────────────────────────────────────────

class InspectionReportUploadView(APIView):
    """
    POST /api/services/<pk>/upload-report/

    Inspector uploads the inspection report PDF/file after completing the job.
    Stays in DRF because it's a file upload.
    """
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, pk):
        try:
            inspection = HomeInspection.objects.select_related(
                'service_request__requester'
            ).get(
                service_request__pk=pk,
                service_request__provider=request.user,
            )
        except HomeInspection.DoesNotExist:
            return Response(
                {'detail': 'Inspection not found or you are not the assigned inspector.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        report_file = request.FILES.get('report')
        if not report_file:
            return Response(
                {'detail': 'No file provided.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        inspection.report = report_file
        inspection.report_notes = request.data.get('report_notes', '')
        inspection.save()

        # Notify the requester their report is ready
        Notification.objects.create(
            recipient=inspection.service_request.requester,
            actor=request.user,
            notification_type='service_completed',
            title='Your home inspection report is ready',
            message='The inspector has uploaded your property report.',
            link=f'/services/{pk}',
        )

        return Response(
            {'detail': 'Report uploaded successfully.'},
            status=status.HTTP_200_OK,
        )


# ── Reviews ───────────────────────────────────────────────────────────────────

class ReviewServiceView(generics.CreateAPIView):
    """
    POST /api/services/<pk>/review/
    Requester leaves a rating and review after service is completed.
    """
    serializer_class = ServiceReviewSerializer

    def perform_create(self, serializer):
        sr = ServiceRequest.objects.get(
            pk=self.kwargs['pk'],
            requester=self.request.user,
            status='completed',
        )
        serializer.save(service_request=sr, reviewer=self.request.user)


# ── Service Provider Registration ─────────────────────────────────────────────

class ServiceProviderProfileListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/services/provider-profiles/  — list my registered service types
    POST /api/services/provider-profiles/  — register as a new service provider
    """
    serializer_class = ServiceProviderProfileSerializer

    def get_queryset(self):
        return ServiceProviderProfile.objects.filter(user=self.request.user)


class ServiceProviderProfileDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET    /api/services/provider-profiles/<pk>/  — get a specific profile
    PATCH  /api/services/provider-profiles/<pk>/  — update bio or toggle active
    DELETE /api/services/provider-profiles/<pk>/  — deregister from a service type
    """
    serializer_class = ServiceProviderProfileSerializer

    def get_queryset(self):
        return ServiceProviderProfile.objects.filter(user=self.request.user)


# ── Migration Specialist Application ─────────────────────────────────────────

class MigrationSpecialistApplyView(generics.CreateAPIView):
    """
    POST /api/services/specialist/apply/
    Submit an application to become a migration specialist.
    Admin will review and approve or reject.
    """
    serializer_class = MigrationSpecialistApplicationSerializer


class MigrationSpecialistApplicationStatusView(generics.RetrieveAPIView):
    """
    GET /api/services/specialist/my-application/
    Check the status of your specialist application (pending/approved/rejected).
    """
    serializer_class = MigrationSpecialistApplicationSerializer

    def get_object(self):
        return MigrationSpecialistApplication.objects.get(user=self.request.user)