from rest_framework import generics, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.utils import timezone
from django.conf import settings as django_settings
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from asgiref.sync import async_to_sync
import uuid
import logging
from .airport_data import get_airports_by_country, get_supported_countries
from .distance_utils import (
    calculate_distance_between_addresses,
    calculate_distance_from_coords,
    calculate_price_based_on_distance,
    get_coordinates_from_address,
    geocode_airport
)

from .models import (
    ServiceRequest, ServiceReview, AirportPickup,
    HomeInspection, ChaperoneService, ServiceProviderProfile,
    MigrationSpecialistApplication, DistanceCalculationLog,
    Property, PropertyImage,
)
from .serializers import (
    ServiceRequestSerializer, ServiceReviewSerializer,
    ServiceProviderProfileSerializer,
    MigrationSpecialistApplicationSerializer,
    PropertySerializer, PropertyCreateUpdateSerializer, PropertyImageSerializer,
)
from notifications.models import Notification

logger = logging.getLogger(__name__)

try:
    from channels.layers import get_channel_layer
    channel_layer = get_channel_layer()
except Exception:
    channel_layer = None


def _broadcast(group, event_type, payload):
    """Send a WebSocket event. Silently skips if Redis/channel layer is unavailable."""
    if channel_layer is None:
        return
    try:
        async_to_sync(channel_layer.group_send)(group, {
            'type': event_type,
            'payload': payload,
        })
    except Exception as exc:
        logger.warning("WebSocket broadcast failed (%s): %s", group, exc)


# ── Uber/Bolt-style pricing ──────────────────────────────────────────────────
#   final fare = max(min_fare, flag_drop_fee + distance_km × per_km_rate)
#   No large "base price" — price scales with distance like real ride-hailing apps.

PER_KM_RATES = {
    # Calibrated to match real Uber/Bolt pricing (Nov 2025)
    ('NG', 'regular'): 700,    ('NG', 'premium'): 1_200,
    ('NG', 'van'):     1_700,  ('NG', 'bus'):     2_200,
    ('GH', 'regular'): 12,     ('GH', 'premium'): 20,
    ('GH', 'van'):     28,     ('GH', 'bus'):     40,
    ('KE', 'regular'): 130,    ('KE', 'premium'): 220,
    ('KE', 'van'):     300,    ('KE', 'bus'):     420,
    ('ZA', 'regular'): 18,     ('ZA', 'premium'): 30,
    ('ZA', 'van'):     42,     ('ZA', 'bus'):     58,
    ('UG', 'regular'): 4_000,  ('UG', 'premium'): 6_500,
    ('UG', 'van'):     9_000,  ('UG', 'bus'):     13_000,
    ('ZW', 'regular'): 2,      ('ZW', 'premium'): 3.5,
    ('ZW', 'van'):     5,      ('ZW', 'bus'):     8,
    ('CM', 'regular'): 700,    ('CM', 'premium'): 1_200,
    ('CM', 'van'):     1_700,  ('CM', 'bus'):     2_200,
    ('IN', 'regular'): 40,     ('IN', 'premium'): 70,
    ('IN', 'van'):     100,    ('IN', 'bus'):     140,
    ('NP', 'regular'): 80,     ('NP', 'premium'): 130,
    ('NP', 'van'):     180,    ('NP', 'bus'):     250,
    ('CN', 'regular'): 6,      ('CN', 'premium'): 10,
    ('CN', 'van'):     14,     ('CN', 'bus'):     20,
    ('GB', 'regular'): 2.50,   ('GB', 'premium'): 4,
    ('GB', 'van'):     5.50,   ('GB', 'bus'):     8,
    ('FR', 'regular'): 2.50,   ('FR', 'premium'): 4,
    ('FR', 'van'):     5.50,   ('FR', 'bus'):     8,
    ('ES', 'regular'): 2.50,   ('ES', 'premium'): 4,
    ('ES', 'van'):     5.50,   ('ES', 'bus'):     8,
    ('PT', 'regular'): 2.50,   ('PT', 'premium'): 4,
    ('PT', 'van'):     5.50,   ('PT', 'bus'):     8,
    ('CY', 'regular'): 2.50,   ('CY', 'premium'): 4,
    ('CY', 'van'):     5.50,   ('CY', 'bus'):     8,
    ('US', 'regular'): 2.50,   ('US', 'premium'): 4,
    ('US', 'van'):     5.50,   ('US', 'bus'):     8,
    ('CA', 'regular'): 3,      ('CA', 'premium'): 5,
    ('CA', 'van'):     7,      ('CA', 'bus'):     10,
    ('AU', 'regular'): 3.50,   ('AU', 'premium'): 6,
    ('AU', 'van'):     8,      ('AU', 'bus'):     12,
}

FALLBACK_PER_KM = {'regular': 2, 'premium': 3, 'van': 4, 'bus': 6}

FLAG_DROP_FEES = {
    'NG': 500, 'GH': 10, 'KE': 200, 'ZA': 30, 'UG': 3_000,
    'ZW': 5, 'CM': 1_000, 'IN': 50, 'NP': 100, 'CN': 20,
    'GB': 3, 'FR': 3, 'ES': 3, 'PT': 3, 'CY': 3,
    'US': 3, 'CA': 4, 'AU': 5,
}

MINIMUM_FARES = {
    'NG': 2_000, 'GH': 30, 'KE': 500, 'ZA': 80, 'UG': 5_000,
    'ZW': 10, 'CM': 2_000, 'IN': 100, 'NP': 200, 'CN': 30,
    'GB': 5, 'FR': 5, 'ES': 5, 'PT': 5, 'CY': 5,
    'US': 5, 'CA': 7, 'AU': 8,
}

VEHICLE_TYPES = ['regular', 'premium', 'van', 'bus']


def _validate_coords(lat_raw, lon_raw):
    """Validate and parse coordinate values. Returns (float, float) or (None, None)."""
    try:
        lat = float(lat_raw) if lat_raw else None
        lon = float(lon_raw) if lon_raw else None
        if lat is not None and not (-90 <= lat <= 90):
            lat = None
        if lon is not None and not (-180 <= lon <= 180):
            lon = None
        return lat, lon
    except (TypeError, ValueError):
        return None, None


def get_vehicle_rate(country_code: str, vehicle_type: str) -> float:
    """Per-km rate for a given country + vehicle type."""
    return PER_KM_RATES.get(
        (country_code.upper(), vehicle_type.lower()),
        FALLBACK_PER_KM.get(vehicle_type.lower(), 2),
    )


def get_flag_drop(country_code: str) -> float:
    return FLAG_DROP_FEES.get(country_code.upper(), 0)


def get_min_fare(country_code: str) -> float:
    return MINIMUM_FARES.get(country_code.upper(), 0)


# ── Distance Calculation Endpoints ───────────────────────────────────────────

class CalculateDistanceView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        import time
        start_time = time.time()
        
        pickup_address = request.data.get('pickup_address')
        pickup_city = request.data.get('pickup_city')
        pickup_country = request.data.get('pickup_country')
        arrival_address = request.data.get('arrival_address')
        arrival_city = request.data.get('arrival_city')
        arrival_country = request.data.get('arrival_country')
        vehicle_type = request.data.get('vehicle_type', 'regular')
        
        # City is optional — geocoding works with just address + country
        if not all([pickup_address, pickup_country, 
                   arrival_address, arrival_country]):
            return Response(
                {'detail': 'pickup_address, pickup_country, arrival_address, and arrival_country are required.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Prefer coordinates from frontend autocomplete; fall back to geocoding
        arrival_lat = request.data.get('arrival_lat')
        arrival_lon = request.data.get('arrival_lon')
        pickup_lat = request.data.get('pickup_lat')
        pickup_lon = request.data.get('pickup_lon')

        _plat, _plon = _validate_coords(pickup_lat, pickup_lon)
        _alat, _alon = _validate_coords(arrival_lat, arrival_lon)

        if _plat is not None and _alat is not None:
            # Both coordinates provided — skip geocoding entirely
            distance_data = calculate_distance_from_coords(
                _plat, _plon, _alat, _alon,
            )
        elif _alat is not None:
            # Only destination coords — geocode the airport
            pickup_coords = get_coordinates_from_address(
                pickup_address, pickup_city or '', pickup_country
            )
            if pickup_coords:
                distance_data = calculate_distance_from_coords(
                    pickup_coords[0], pickup_coords[1],
                    _alat, _alon,
                )
            else:
                distance_data = None
        else:
            distance_data = calculate_distance_between_addresses(
                pickup_address, pickup_city, pickup_country,
                arrival_address, arrival_city, arrival_country
            )
        
        if not distance_data:
            return Response(
                {'detail': 'Could not calculate distance between the provided addresses.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Use the trip's country (pickup) for pricing, fall back to user profile country
        country_code = pickup_country or request.user.current_country or 'NG'
        per_km_rate = get_vehicle_rate(country_code, vehicle_type)
        flag_drop = get_flag_drop(country_code)
        min_fare = get_min_fare(country_code)

        total, distance_charge, flag_drop_fee = calculate_price_based_on_distance(
            per_km_rate, distance_data['distance_km'],
            flag_drop_fee=flag_drop, min_fare=min_fare,
        )

        response_data = {
            'distance_km':       distance_data['distance_km'],
            'duration_min':      distance_data['duration_min'],
            'distance_type':     distance_data.get('distance_type', 'unknown'),
            'flag_drop_fee':     float(flag_drop_fee),
            'per_km_rate':       float(per_km_rate),
            'distance_charge':   float(distance_charge),
            'minimum_fare':      float(min_fare),
            'total_price':       float(total),
            'pickup_coords':     distance_data.get('pickup_coords'),
            'arrival_coords':    distance_data.get('arrival_coords'),
        }

        return Response(response_data, status=status.HTTP_200_OK)


class GeocodeAddressView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        address = request.data.get('address')
        city = request.data.get('city')
        country = request.data.get('country')
        
        if not all([address, city, country]):
            return Response(
                {'detail': 'Address, city, and country are required.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        coords = get_coordinates_from_address(address, city, country)
        
        if not coords:
            return Response(
                {'detail': 'Could not geocode the provided address.'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        return Response({
            'latitude': coords[0],
            'longitude': coords[1],
            'address': f"{address}, {city}, {country}"
        }, status=status.HTTP_200_OK)


class EstimateDriverArrivalView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        city = request.user.city
        default_estimates = {
            'Lagos': 15,
            'Abuja': 12,
            'Accra': 10,
            'Nairobi': 18,
        }
        
        estimated_minutes = default_estimates.get(city, 20)
        
        return Response({
            'estimated_arrival_minutes': estimated_minutes,
            'estimated_arrival_seconds': estimated_minutes * 60,
            'message': f'Estimated driver arrival in {estimated_minutes} minutes'
        }, status=status.HTTP_200_OK)


class UpdateDriverLocationView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        is_driver = ServiceProviderProfile.objects.filter(
            user=request.user,
            service_type='airport_pickup',
            is_active=True
        ).exists()
        
        if not is_driver:
            return Response(
                {'detail': 'Only drivers can update location.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        return Response({
            'status': 'success',
            'message': 'Location updated successfully',
            'timestamp': timezone.now().isoformat()
        }, status=status.HTTP_200_OK)


# ── Service Requests ─────────────────────────────────────────────────────────

class ServiceRequestListCreateView(generics.ListCreateAPIView):
    serializer_class = ServiceRequestSerializer

    def get_queryset(self):
        return ServiceRequest.objects.filter(
            requester=self.request.user
        ).select_related('provider').prefetch_related('airport_pickup_details').order_by('-created_at')

    def perform_create(self, serializer):
        sr = serializer.save(requester=self.request.user)
        # Fall back to user's profile city if the payload didn't include one
        if not sr.city:
            sr.city = self.request.user.city or ''
            sr.save(update_fields=['city'])
        city_key = (sr.city or '').lower()
        if city_key and sr.country_code:
            _broadcast(
                group=f'available_services_{sr.country_code}_{city_key}_{sr.service_type}',
                event_type='new_service_request',
                payload={
                    'id':           sr.id,
                    'service_id':   sr.id,
                    'service_type': sr.service_type,
                    'city':         sr.city,
                    'country_code': sr.country_code,
                    'description':  sr.description,
                    'price':        str(sr.price) if sr.price else None,
                    'currency':     sr.currency,
                    'airport':      getattr(getattr(sr, 'airport_pickup_details', None), 'airport', None),
                    'created_at':   sr.created_at.isoformat(),
                },
            )


class ServiceRequestDetailView(generics.RetrieveUpdateAPIView):
    serializer_class = ServiceRequestSerializer

    def get_queryset(self):
        return ServiceRequest.objects.filter(requester=self.request.user)


class DriverServiceRequestDetailView(generics.RetrieveAPIView):
    """GET /api/services/<pk>/driver-view/

    Lets a registered driver fetch full details of any pending or accepted
    service request — used on the confirmation page before claiming.
    The requester filter is intentionally omitted so drivers can read
    rides they didn't create.
    """
    serializer_class = ServiceRequestSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        from rest_framework.exceptions import PermissionDenied, NotFound

        pk = self.kwargs['pk']

        # Only active providers may use this endpoint
        is_driver = ServiceProviderProfile.objects.filter(
            user=self.request.user,
            is_active=True,
        ).exists()
        if not is_driver:
            raise PermissionDenied('Only registered providers can view this.')

        # Use a clean DRF NotFound (JSON) instead of Django's HTML 404 debug page
        try:
            return (
                ServiceRequest.objects
                .select_related('requester')
                .prefetch_related('airport_pickup_details')
                .get(pk=pk)
            )
        except ServiceRequest.DoesNotExist:
            raise NotFound('Service request not found.')


class UpdateServiceRequestDistanceView(APIView):
    """PATCH /api/services/<pk>/update-distance/

    Saves addresses **and** calculates distance + price, persisting every
    field the rest of the flow needs (distance_km, multiplier, base price, etc.).
    """
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, pk):
        try:
            sr = ServiceRequest.objects.get(pk=pk, requester=request.user)
        except ServiceRequest.DoesNotExist:
            return Response(
                {'detail': 'Service request not found.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        pickup_address = request.data.get('pickup_address')
        arrival_address = request.data.get('arrival_address')

        if pickup_address:
            sr.pickup_address = pickup_address
        if arrival_address:
            sr.arrival_address = arrival_address

        # ── Calculate distance + price ──────────────────────────────────
        country_code = sr.country_code or request.user.current_country or 'NG'
        city = sr.city or request.user.city or ''

        # Prefer coordinates from frontend autocomplete; fall back to geocoding
        arrival_lat = request.data.get('arrival_lat')
        arrival_lon = request.data.get('arrival_lon')
        pickup_lat = request.data.get('pickup_lat')
        pickup_lon = request.data.get('pickup_lon')

        _plat, _plon = _validate_coords(pickup_lat, pickup_lon)
        _alat, _alon = _validate_coords(arrival_lat, arrival_lon)

        if pickup_address and arrival_address:
            try:
                if _plat is not None and _alat is not None:
                    # Both coordinates provided — skip geocoding entirely
                    distance_data = calculate_distance_from_coords(
                        _plat, _plon, _alat, _alon,
                    )
                elif _alat is not None:
                    # Only destination coords — geocode the airport
                    pickup_coords = get_coordinates_from_address(
                        pickup_address, city or '', country_code
                    )
                    if pickup_coords:
                        distance_data = calculate_distance_from_coords(
                            pickup_coords[0], pickup_coords[1],
                            _alat, _alon,
                        )
                    else:
                        distance_data = None
                else:
                    distance_data = calculate_distance_between_addresses(
                        pickup_address, city, country_code,
                        arrival_address, city, country_code,
                    )

                if distance_data:
                    sr.distance_km = distance_data['distance_km']
                    sr.estimated_duration_min = int(distance_data['duration_min'])
                    sr.distance_calculation_method = distance_data.get('distance_type', 'routing')

                    if distance_data.get('pickup_coords'):
                        sr.pickup_latitude = distance_data['pickup_coords'][0]
                        sr.pickup_longitude = distance_data['pickup_coords'][1]
                    if distance_data.get('arrival_coords'):
                        sr.arrival_latitude = distance_data['arrival_coords'][0]
                        sr.arrival_longitude = distance_data['arrival_coords'][1]

                    # Price calculation
                    vehicle_type = request.data.get('vehicle_type', 'regular')
                    per_km_rate = get_vehicle_rate(country_code, vehicle_type)
                    flag_drop = get_flag_drop(country_code)
                    min_fare = get_min_fare(country_code)

                    total, distance_charge, flag_drop_fee = calculate_price_based_on_distance(
                        per_km_rate, distance_data['distance_km'],
                        flag_drop_fee=flag_drop, min_fare=min_fare,
                    )

                    sr.price = total
                    sr.original_base_price = float(flag_drop_fee)
                    sr.distance_price_multiplier = round(float(per_km_rate), 2)
                    sr.currency = django_settings.COUNTRY_CURRENCY_MAP.get(country_code, 'USD')

                    logger.info(
                        'Distance calculated for %s: %.1fkm, price=%s %s',
                        sr.id, float(sr.distance_km), sr.price, sr.currency,
                    )
            except Exception as exc:
                logger.error('Distance/price calculation failed for %s: %s', sr.id, exc)
                # Save addresses even if calculation fails — flow isn't blocked

        sr.save()
        return Response(
            ServiceRequestSerializer(sr, context={'request': request}).data,
            status=status.HTTP_200_OK,
        )


class TrackDriverLocationView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request, pk):
        try:
            sr = ServiceRequest.objects.get(pk=pk)
        except ServiceRequest.DoesNotExist:
            return Response(
                {'detail': 'Service request not found.'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        if sr.requester != request.user and sr.provider != request.user:
            return Response(
                {'detail': 'You do not have access to this service.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        return Response({
            'service_id': sr.id,
            'status': sr.status,
        }, status=status.HTTP_200_OK)


def get_driver_vehicle_details(driver_user):
    try:
        profile = ServiceProviderProfile.objects.get(
            user=driver_user,
            service_type='airport_pickup'
        )
        return {
            'model': profile.vehicle_model,
            'color': profile.vehicle_colour,
            'plate_number': profile.license_plate_number,
        }
    except ServiceProviderProfile.DoesNotExist:
        return None


# ── Available Services Pool ──────────────────────────────────────────────────

class AvailableServicesView(generics.ListAPIView):
    pagination_class = None
    serializer_class = ServiceRequestSerializer

    def get_queryset(self):
        user = self.request.user
        provider_types = ServiceProviderProfile.objects.filter(
            user=user,
            is_active=True,
        ).values_list('service_type', flat=True)

        if not provider_types:
            return ServiceRequest.objects.none()

        return ServiceRequest.objects.filter(
            status='pending',
            service_type__in=provider_types,
        ).exclude(requester=user).select_related('requester')


class ClaimServiceView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        user = request.user

        try:
            with transaction.atomic():
                sr = ServiceRequest.objects.select_for_update().get(
                    pk=pk, status='pending'
                )

                if sr.requester == user:
                    return Response(
                        {'detail': 'You cannot claim your own request.'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                sr.provider = user
                sr.status = 'accepted'
                sr.save()

        except ServiceRequest.DoesNotExist:
            return Response(
                {'detail': 'This service is no longer available.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        _broadcast(
            group=f'available_services_{sr.country_code}_{sr.city.lower()}_{sr.service_type}',
            event_type='service_claimed',
            payload={'service_id': sr.id},
        )

        return Response(
            ServiceRequestSerializer(sr, context={'request': request}).data,
            status=status.HTTP_200_OK,
        )


class MyProviderJobsView(generics.ListAPIView):
    serializer_class = ServiceRequestSerializer

    def get_queryset(self):
        return ServiceRequest.objects.filter(
            provider=self.request.user
        ).select_related('requester').order_by('-created_at')


class UpcomingPickupsView(generics.ListAPIView):
    serializer_class = ServiceRequestSerializer

    def get_queryset(self):
        return ServiceRequest.objects.filter(
            provider=self.request.user,
            service_type='airport_pickup',
            status__in=['accepted', 'in_progress'],
        ).select_related('requester', 'airport_pickup_details')


class UpdateTripStatusView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, pk):
        new_status = request.data.get('status')
        notes = request.data.get('notes', '')

        STATUS_MAP = {
            'en_route': 'in_progress',
            'arrived': 'in_progress',
            'picked_up': 'in_progress',
            'completed': 'completed',
        }
        mapped_status = STATUS_MAP.get(new_status, new_status)

        try:
            sr = ServiceRequest.objects.get(pk=pk)
        except ServiceRequest.DoesNotExist:
            return Response(
                {'detail': 'Service request not found.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        if sr.provider != request.user:
            return Response(
                {'detail': 'Only the assigned provider can update this trip.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        sr.status = mapped_status
        if notes:
            sr.notes = f"{sr.notes}\n{notes}".strip() if sr.notes else notes
        sr.save()

        return Response({
            'service_id': sr.id,
            'status': sr.status,
            'message': f'Trip status updated to {mapped_status}',
        }, status=status.HTTP_200_OK)


class InspectionReportUploadView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, pk):
        return Response({'detail': 'Report uploaded.'}, status=status.HTTP_200_OK)


class ReviewServiceView(generics.CreateAPIView):
    serializer_class = ServiceReviewSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        sr = ServiceRequest.objects.get(
            pk=self.kwargs['pk'],
            requester=self.request.user,
            status__in=['completed', 'in_progress'],
        )
        serializer.save(service_request=sr, reviewer=self.request.user)


class RatePassengerView(APIView):
    """PATCH /api/services/<pk>/rate-passenger/

    Allows the driver (provider) to rate the passenger after trip completion.
    Saves passenger_rating and passenger_review_comment on the ServiceRequest.
    """
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, pk):
        try:
            sr = ServiceRequest.objects.get(
                pk=pk,
                provider=request.user,
                status__in=['completed', 'in_progress'],
            )
        except ServiceRequest.DoesNotExist:
            return Response(
                {'detail': 'Trip not found for this driver.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        rating = request.data.get('rating')
        if rating is not None:
            try:
                rating = int(rating)
                if rating < 1 or rating > 5:
                    raise ValueError
            except (TypeError, ValueError):
                return Response(
                    {'detail': 'Rating must be an integer between 1 and 5.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            sr.passenger_rating = rating

        comment = request.data.get('comment', '')
        if comment:
            sr.passenger_review_comment = comment

        sr.save(update_fields=['passenger_rating', 'passenger_review_comment'])
        return Response({'status': 'ok', 'passenger_rating': sr.passenger_rating})


class ServiceProviderProfileListCreateView(generics.ListCreateAPIView):
    serializer_class = ServiceProviderProfileSerializer
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return ServiceProviderProfile.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user, is_active=True)


class ServiceProviderProfileDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = ServiceProviderProfileSerializer
    parser_classes = [MultiPartParser, FormParser]

    def get_queryset(self):
        return ServiceProviderProfile.objects.filter(user=self.request.user)


class MigrationSpecialistApplyView(generics.CreateAPIView):
    serializer_class = MigrationSpecialistApplicationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class MigrationSpecialistApplicationStatusView(generics.RetrieveAPIView):
    serializer_class = MigrationSpecialistApplicationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return MigrationSpecialistApplication.objects.get(user=self.request.user)


class VehiclePricingView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        country_code = request.query_params.get('country') or request.user.current_country or 'NG'
        currency = django_settings.COUNTRY_CURRENCY_MAP.get(country_code, 'USD')
        flag_drop = get_flag_drop(country_code)
        min_fare = get_min_fare(country_code)

        vehicles = [
            {
                'id': vtype,
                'per_km_rate': get_vehicle_rate(country_code, vtype),
                'flag_drop_fee': float(flag_drop),
                'minimum_fare': float(min_fare),
            }
            for vtype in VEHICLE_TYPES
        ]

        return Response({
            'currency': currency,
            'country_code': country_code,
            'vehicles': vehicles,
        })


class ConfirmVehicleView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, pk):
        vehicle_type = request.data.get('vehicle_type')
        if not vehicle_type:
            return Response(
                {'detail': 'vehicle_type is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            sr = ServiceRequest.objects.get(pk=pk, requester=request.user)
        except ServiceRequest.DoesNotExist:
            return Response(
                {'detail': 'Service request not found.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        country_code = sr.country_code or request.user.current_country or 'NG'
        per_km_rate = get_vehicle_rate(country_code, vehicle_type)
        flag_drop = get_flag_drop(country_code)
        min_fare = get_min_fare(country_code)
        currency = django_settings.COUNTRY_CURRENCY_MAP.get(country_code, 'USD')

        if sr.price and sr.price > 0:
            total = float(sr.price)
        elif sr.distance_km:
            total, distance_charge, flag_drop_fee = calculate_price_based_on_distance(
                per_km_rate, float(sr.distance_km),
                flag_drop_fee=flag_drop, min_fare=min_fare,
            )
        else:
            total = float(min_fare) if min_fare > 0 else float(flag_drop)

        sr.original_base_price = sr.original_base_price or float(flag_drop)
        sr.price = total
        sr.currency = currency
        sr.save()

        return Response({
            'id': sr.id,
            'vehicle_type': vehicle_type,
            'price': str(sr.price),
            'currency': currency,
            'flag_drop_fee': float(flag_drop),
            'per_km_rate': float(per_km_rate),
            'distance_km': float(sr.distance_km) if sr.distance_km else None,
            'minimum_fare': float(min_fare),
        }, status=status.HTTP_200_OK)


class AirportListView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        country = request.query_params.get("country")
        airports = get_airports_by_country(country)
        return Response({
            "airports": airports,
            "supported_countries": get_supported_countries(),
        })


# ═══════════════════════════════════════════════════════════════════════════════
# PROPERTY VIEWS
# ═══════════════════════════════════════════════════════════════════════════════

class PropertyListCreateView(generics.ListCreateAPIView):
    """List user's properties or create a new property"""
    serializer_class = PropertyCreateUpdateSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return Property.objects.filter(owner=self.request.user)
    
    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)


class PropertyDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update, or delete a property.
    
    Owners can fully manage their properties.
    Other authenticated users can only view published properties.
    """
    serializer_class = PropertyCreateUpdateSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_object(self):
        obj = get_object_or_404(Property, pk=self.kwargs['pk'])
        user = self.request.user
        if obj.owner == user:
            return obj
        if self.request.method in permissions.SAFE_METHODS and obj.is_published and obj.status == 'published':
            return obj
        self.permission_denied(self.request, message='Property not found.')


class PublishPropertyView(APIView):
    """Publish a property (change status from draft to published)"""
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request, pk):
        try:
            prop = Property.objects.get(pk=pk, owner=request.user)
        except Property.DoesNotExist:
            return Response(
                {'detail': 'Property not found.'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        prop.status = 'published'
        prop.is_published = True
        prop.save()
        
        return Response({
            'id': prop.id,
            'status': prop.status,
            'message': 'Property published successfully!'
        }, status=status.HTTP_200_OK)


class UploadPropertyImageView(APIView):
    """Upload property images"""
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    
    def post(self, request, pk):
        try:
            prop = Property.objects.get(pk=pk, owner=request.user)
        except Property.DoesNotExist:
            return Response(
                {'detail': 'Property not found.'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        def absurl(path):
            return request.build_absolute_uri(path) if path else None
        
        images = request.FILES.getlist('images')
        urls = []
        
        for idx, image in enumerate(images):
            ext = image.name.split('.')[-1]
            filename = f"properties/{prop.id}/{uuid.uuid4()}.{ext}"
            filepath = default_storage.save(filename, ContentFile(image.read()))
            url = absurl(default_storage.url(filepath))
            urls.append(url)
            
            PropertyImage.objects.create(
                property=prop,
                image_url=url,
                order=idx
            )
        
        # Also update the JSONField so the frontend can find them
        prop.images = list(prop.images or []) + urls
        prop.save(update_fields=['images'])
        
        return Response({
            'images': urls,
            'message': f'{len(images)} image(s) uploaded successfully.'
        }, status=status.HTTP_200_OK)


class DeletePropertyImageView(APIView):
    """Delete a property image"""
    permission_classes = [permissions.IsAuthenticated]
    
    def delete(self, request, pk, image_id):
        try:
            prop = Property.objects.get(pk=pk, owner=request.user)
            image = PropertyImage.objects.get(pk=image_id, property=prop)
        except (Property.DoesNotExist, PropertyImage.DoesNotExist):
            return Response(
                {'detail': 'Property or image not found.'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        if image.image_url:
            default_storage.delete(image.image_url.replace('/media/', ''))
        image.delete()
        
        return Response(status=status.HTTP_204_NO_CONTENT)


class PropertySearchView(APIView):
    """Search published properties — filtered only by city/location.

    All other filters (price, type, bedrooms, duration, etc.) are ignored
    so tenants see everything available in their target area.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        filters = request.data

        queryset = Property.objects.filter(is_published=True, status='published')

        # ── Location (the only filter that matters) ──────────────────────
        city = filters.get('city', '').strip()
        if city:
            queryset = queryset.filter(city__icontains=city)

        state = filters.get('state', '').strip()
        if state:
            queryset = queryset.filter(state__icontains=state)

        # ── Pagination ────────────────────────────────────────────────────
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 10))
        start = (page - 1) * page_size
        end = start + page_size

        total = queryset.count()

        # ── Ordering ──────────────────────────────────────────────────────
        queryset = queryset.order_by('-created_at')

        results = queryset[start:end]

        serializer = PropertySerializer(results, many=True)

        return Response({
            'results': serializer.data,
            'total': total,
            'page': page,
            'totalPages': (total + page_size - 1) // page_size,
        }, status=status.HTTP_200_OK)

# ── Chaperone Views ─────────────────────────────────────────────────────────

class AvailableChaperonesView(generics.ListAPIView):
    """GET /api/services/chaperones/available/
    
    Lists all active chaperone providers for users to browse and book.
    """
    serializer_class = ServiceProviderProfileSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = ServiceProviderProfile.objects.filter(
            service_type='chaperone',
            is_active=True,
        ).select_related('user')

        city = self.request.query_params.get('city')
        country_code = self.request.query_params.get('country_code')
        offers_translation = self.request.query_params.get('offers_translation')

        if city:
            qs = qs.filter(city__iexact=city)
        if country_code:
            qs = qs.filter(country_code__iexact=country_code)
        if offers_translation and offers_translation.lower() == 'true':
            qs = qs.filter(offers_translation_service=True)

        return qs


class BroadcastChaperoneServiceView(APIView):
    """POST /api/services/<pk>/broadcast-chaperone/

    Called after a user books chaperone services.
    Broadcasts to all chaperones in the same country/city via WebSocket and
    creates Notification records so they see it in their notification centre.
    Also sends a confirmation notification to the requester.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        sr = get_object_or_404(ServiceRequest, pk=pk, requester=request.user, service_type='chaperone')

        if sr.status != 'pending':
            return Response(
                {'detail': f'Service is already {sr.status}.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        city_key = sr.city.lower() if sr.city else ''

        # ── 1. WebSocket broadcast to chaperone groups ─────────────────────
        group = f'available_services_{sr.country_code}_{city_key}_chaperone'
        _broadcast(group, 'new_service_request', {
            'id':           sr.id,
            'service_id':   sr.id,
            'service_type': 'chaperone',
            'country_code': sr.country_code,
            'city':         sr.city,
            'description':  sr.description,
            'price':        str(sr.price) if sr.price else None,
            'currency':     sr.currency,
            'help_type':    getattr(getattr(sr, 'chaperone_details', None), 'help_type', None),
            'created_at':   sr.created_at.isoformat() if sr.created_at else None,
        })

        # ── 2. Persist a Notification for every chaperone in the area ──────
        from notifications.models import Notification
        from services.models import ServiceProviderProfile

        chaperones = (
            ServiceProviderProfile.objects
            .filter(
                country_code=sr.country_code,
                service_type='chaperone',
                is_active=True,
            )
            .exclude(user=sr.requester)
            .select_related('user')
        )
        if sr.city:
            same_city = chaperones.filter(city__iexact=sr.city)
            if same_city.exists():
                chaperones = same_city

        help_type_display = dict(ChaperoneService.HELP_TYPES).get(
            getattr(getattr(sr, 'chaperone_details', None), 'help_type', ''), 'General'
        )
        notif_link = '/dashboard/chaperone'
        notif_title = 'New Chaperone Service Request'
        notif_msg = (
            f'A user needs {help_type_display} assistance in {sr.city or sr.country_code}. '
            f'{sr.description}'
        )

        notifications = []
        for profile in chaperones:
            notifications.append(Notification(
                recipient=profile.user,
                actor=request.user,
                notification_type='service_accepted',
                title=notif_title,
                message=notif_msg,
                link=notif_link,
            ))

        # Also notify the requester that their booking was received
        notifications.append(Notification(
            recipient=request.user,
            actor=request.user,
            notification_type='service_accepted',
            title='Chaperone Booking Confirmed',
            message=f'Your request for {help_type_display} assistance in {sr.city or sr.country_code} has been submitted. A chaperone will respond shortly.',
            link='/dashboard/chaperone',
        ))

        if notifications:
            Notification.objects.bulk_create(notifications)

        # ── 3. Send real-time WebSocket notifications ─────────────────────
        for profile in chaperones:
            try:
                from asgiref.sync import async_to_sync
                from channels.layers import get_channel_layer
                channel_layer = get_channel_layer()
                if channel_layer:
                    async_to_sync(channel_layer.group_send)(
                        f'user_notifications_{profile.user.id}',
                        {
                            'type': 'new_notification',
                            'payload': {
                                'title': notif_title,
                                'message': notif_msg,
                                'link': notif_link,
                            },
                        }
                    )
            except Exception:
                pass

        return Response({
            'detail': f'Job broadcast to {max(len(chaperones), 0)} chaperone(s).',
            'chaperones_notified': len(chaperones),
        }, status=status.HTTP_200_OK)


class BroadcastServiceView(APIView):
    """
    POST /api/services/<pk>/broadcast/

    Rider calls this after confirming vehicle on the direction page.
    Broadcasts the job to all drivers in the area via WebSocket and
    creates a Notification record for each driver so they see it in
    their notification centre even if offline.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        sr = get_object_or_404(ServiceRequest, pk=pk, requester=request.user)

        if sr.status != 'pending':
            return Response(
                {'detail': f'Service is already {sr.status}.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ── 1. WebSocket broadcast to driver groups ───────────────────────
        group = (
            f'available_services_{sr.country_code}'
            f'_{sr.city.lower() if sr.city else ""}_{sr.service_type}'
        )
        _broadcast(group, 'new_service_request', {
            'id':           sr.id,
            'service_id':   sr.id,
            'service_type': sr.service_type,
            'country_code': sr.country_code,
            'city':         sr.city,
            'description':  sr.description,
            'price':        str(sr.price) if sr.price else None,
            'currency':     sr.currency,
            'airport':      sr.airport_pickup_details.airport if sr.airport_pickup_details else None,
            'created_at':   sr.created_at.isoformat() if sr.created_at else None,
        })

        # ── 2. Persist a Notification for every driver in the area ────────
        from notifications.models import Notification
        from services.models import ServiceProviderProfile

        drivers = (
            ServiceProviderProfile.objects
            .filter(
                country_code=sr.country_code,
                service_type=sr.service_type,
                is_active=True,
            )
            .exclude(user=sr.requester)
            .select_related('user')
        )
        # Prefer same-city drivers, but don't exclude others entirely
        if sr.city:
            same_city = drivers.filter(city__iexact=sr.city)
            if same_city.exists():
                drivers = same_city

        notif_link = f'/dashboard/airport-pickup/drivers-airport-pickup/drivers-pickup'
        notif_title = 'New Airport Pickup Request'
        notif_msg = (
            f'A passenger needs a ride from '
            f'{sr.airport_pickup_details.airport if sr.airport_pickup_details else sr.description} '
            f'to {sr.notes or "destination"}.'
        )

        created = 0
        notifications = []
        for profile in drivers:
            notifications.append(Notification(
                recipient=profile.user,
                actor=request.user,
                notification_type='service_accepted',
                title=notif_title,
                message=notif_msg,
                link=notif_link,
            ))
        if notifications:
            Notification.objects.bulk_create(notifications)

        for profile in drivers:
            try:
                from asgiref.sync import async_to_sync
                from channels.layers import get_channel_layer
                channel_layer = get_channel_layer()
                if channel_layer:
                    async_to_sync(channel_layer.group_send)(
                        f'user_notifications_{profile.user.id}',
                        {
                            'type': 'new_notification',
                            'payload': {
                                'title': notif_title,
                                'message': notif_msg,
                                'link': notif_link,
                            },
                        }
                    )
            except Exception:
                pass  # non-critical

        return Response({
            'detail': f'Job broadcast to {len(notifications)} driver(s).',
            'drivers_notified': len(notifications),
        }, status=status.HTTP_200_OK)
