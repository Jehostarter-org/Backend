from rest_framework import generics, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
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
    calculate_price_based_on_distance,
    get_coordinates_from_address,
    geocode_airport
)

from .models import (
    ServiceRequest, ServiceReview, AirportPickup,
    HomeInspection, ServiceProviderProfile,
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


# ── Price calculation ─────────────────────────────────────────────────────────

VEHICLE_PRICES = {
    ('NG', 'regular'): 30_000,
    ('NG', 'premium'): 55_000,
    ('NG', 'van'):     75_000,
    ('NG', 'bus'):     95_000,
    ('GH', 'regular'): 350,
    ('GH', 'premium'): 600,
    ('GH', 'van'):     850,
    ('GH', 'bus'):     1_100,
    ('KE', 'regular'): 3_500,
    ('KE', 'premium'): 6_000,
    ('KE', 'van'):     8_500,
    ('KE', 'bus'):     11_000,
    ('ZA', 'regular'): 600,
    ('ZA', 'premium'): 1_000,
    ('ZA', 'van'):     1_500,
    ('ZA', 'bus'):     2_000,
    ('UG', 'regular'): 120_000,
    ('UG', 'premium'): 200_000,
    ('UG', 'van'):     300_000,
    ('UG', 'bus'):     400_000,
    ('ZW', 'regular'): 40,
    ('ZW', 'premium'): 70,
    ('ZW', 'van'):     100,
    ('ZW', 'bus'):     140,
    ('CM', 'regular'): 25_000,
    ('CM', 'premium'): 45_000,
    ('CM', 'van'):     65_000,
    ('CM', 'bus'):     85_000,
    ('IN', 'regular'): 1_500,
    ('IN', 'premium'): 2_800,
    ('IN', 'van'):     4_000,
    ('IN', 'bus'):     5_500,
    ('NP', 'regular'): 2_500,
    ('NP', 'premium'): 4_500,
    ('NP', 'van'):     6_500,
    ('NP', 'bus'):     8_500,
    ('CN', 'regular'): 200,
    ('CN', 'premium'): 380,
    ('CN', 'van'):     550,
    ('CN', 'bus'):     750,
    ('GB', 'regular'): 45,
    ('GB', 'premium'): 75,
    ('GB', 'van'):     110,
    ('GB', 'bus'):     150,
    ('FR', 'regular'): 50,
    ('FR', 'premium'): 85,
    ('FR', 'van'):     125,
    ('FR', 'bus'):     165,
    ('ES', 'regular'): 45,
    ('ES', 'premium'): 80,
    ('ES', 'van'):     115,
    ('ES', 'bus'):     155,
    ('PT', 'regular'): 40,
    ('PT', 'premium'): 70,
    ('PT', 'van'):     100,
    ('PT', 'bus'):     140,
    ('CY', 'regular'): 35,
    ('CY', 'premium'): 60,
    ('CY', 'van'):     90,
    ('CY', 'bus'):     120,
    ('US', 'regular'): 55,
    ('US', 'premium'): 95,
    ('US', 'van'):     140,
    ('US', 'bus'):     190,
    ('CA', 'regular'): 70,
    ('CA', 'premium'): 120,
    ('CA', 'van'):     175,
    ('CA', 'bus'):     235,
    ('AU', 'regular'): 80,
    ('AU', 'premium'): 140,
    ('AU', 'van'):     200,
    ('AU', 'bus'):     270,
}

FALLBACK_PRICES = {
    'regular': 40,
    'premium': 70,
    'van':     100,
    'bus':     140,
}

VEHICLE_TYPES = ['regular', 'premium', 'van', 'bus']


def get_vehicle_price(country_code: str, vehicle_type: str) -> int:
    return VEHICLE_PRICES.get(
        (country_code.upper(), vehicle_type.lower()),
        FALLBACK_PRICES.get(vehicle_type.lower(), 40),
    )


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
        
        if not all([pickup_address, pickup_city, pickup_country, 
                   arrival_address, arrival_city, arrival_country]):
            return Response(
                {'detail': 'All address fields are required.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        distance_data = calculate_distance_between_addresses(
            pickup_address, pickup_city, pickup_country,
            arrival_address, arrival_city, arrival_country
        )
        
        if not distance_data:
            return Response(
                {'detail': 'Could not calculate distance between the provided addresses.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        base_price = get_vehicle_price(request.user.current_country, vehicle_type)
        
        price_per_km_map = {
            'regular': 1.5,
            'premium': 2.5,
            'van': 3.0,
            'bus': 4.0,
        }
        price_per_km = price_per_km_map.get(vehicle_type, 2.0)
        
        final_price = calculate_price_based_on_distance(
            base_price, 
            distance_data['distance_km'],
            price_per_km=price_per_km
        )
        
        is_long_distance = distance_data['distance_km'] > 50
        long_distance_fee = final_price * 0.15 if is_long_distance else 0
        
        response_data = {
            'distance_km': distance_data['distance_km'],
            'duration_min': distance_data['duration_min'],
            'distance_type': distance_data.get('distance_type', 'unknown'),
            'base_price': float(base_price),
            'calculated_price': float(final_price),
            'long_distance_fee': float(long_distance_fee),
            'total_price': float(final_price + long_distance_fee),
            'price_per_km': price_per_km,
            'is_long_distance': is_long_distance,
            'pickup_coords': distance_data.get('pickup_coords'),
            'arrival_coords': distance_data.get('arrival_coords'),
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
        ).select_related('provider').order_by('-created_at')

    def perform_create(self, serializer):
        sr = serializer.save(requester=self.request.user)
        _broadcast(
            group=f'available_services_{sr.country_code}_{sr.city.lower()}_{sr.service_type}',
            event_type='new_service_request',
            payload={
                'service_id':   sr.id,
                'service_type': sr.service_type,
                'city':         sr.city,
                'country_code': sr.country_code,
                'description':  sr.description,
                'created_at':   sr.created_at.isoformat(),
            },
        )


class ServiceRequestDetailView(generics.RetrieveUpdateAPIView):
    serializer_class = ServiceRequestSerializer

    def get_queryset(self):
        return ServiceRequest.objects.filter(requester=self.request.user)


class UpdateServiceRequestDistanceView(APIView):
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
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, pk):
        return Response({'detail': 'Report uploaded.'}, status=status.HTTP_200_OK)


class ReviewServiceView(generics.CreateAPIView):
    serializer_class = ServiceReviewSerializer

    def perform_create(self, serializer):
        sr = ServiceRequest.objects.get(
            pk=self.kwargs['pk'],
            requester=self.request.user,
            status='completed',
        )
        serializer.save(service_request=sr, reviewer=self.request.user)


class ServiceProviderProfileListCreateView(generics.ListCreateAPIView):
    serializer_class = ServiceProviderProfileSerializer
    parser_classes = [MultiPartParser, FormParser]

    def get_queryset(self):
        return ServiceProviderProfile.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class ServiceProviderProfileDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = ServiceProviderProfileSerializer
    parser_classes = [MultiPartParser, FormParser]

    def get_queryset(self):
        return ServiceProviderProfile.objects.filter(user=self.request.user)


class MigrationSpecialistApplyView(generics.CreateAPIView):
    serializer_class = MigrationSpecialistApplicationSerializer

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class MigrationSpecialistApplicationStatusView(generics.RetrieveAPIView):
    serializer_class = MigrationSpecialistApplicationSerializer

    def get_object(self):
        return MigrationSpecialistApplication.objects.get(user=self.request.user)


class VehiclePricingView(APIView):
    def get(self, request):
        country_code = request.user.current_country or 'NG'
        currency = django_settings.COUNTRY_CURRENCY_MAP.get(country_code, 'USD')

        vehicles = [
            {'id': vtype, 'price': get_vehicle_price(country_code, vtype)}
            for vtype in VEHICLE_TYPES
        ]

        return Response({
            'currency': currency,
            'country_code': country_code,
            'vehicles': vehicles,
        })


class ConfirmVehicleView(APIView):
    """
    PATCH /api/services/<pk>/confirm-vehicle/

    Rider picks a vehicle type. Server calculates the final price and saves it.
    """

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
        base_price = get_vehicle_price(country_code, vehicle_type)
        currency = django_settings.COUNTRY_CURRENCY_MAP.get(country_code, 'USD')

        # Apply distance multiplier if distance has been calculated
        final_price = base_price
        if sr.distance_km and sr.distance_price_multiplier and sr.distance_price_multiplier != 1:
            final_price = float(base_price) * float(sr.distance_price_multiplier)

        sr.price = final_price
        sr.currency = currency
        sr.save()

        return Response({
            'id': sr.id,
            'vehicle_type': vehicle_type,
            'price': str(sr.price),
            'currency': currency,
            'base_price': str(base_price),
            'distance_km': float(sr.distance_km) if sr.distance_km else None,
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
    """Retrieve, update, or delete a property"""
    serializer_class = PropertyCreateUpdateSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return Property.objects.filter(owner=self.request.user)


class PublishPropertyView(APIView):
    """Publish a property (change status from draft to published)"""
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request, pk):
        try:
            property = Property.objects.get(pk=pk, owner=request.user)
        except Property.DoesNotExist:
            return Response(
                {'detail': 'Property not found.'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        property.status = 'published'
        property.is_published = True
        property.save()
        
        return Response({
            'id': property.id,
            'status': property.status,
            'message': 'Property published successfully!'
        }, status=status.HTTP_200_OK)


class UploadPropertyImageView(APIView):
    """Upload property images"""
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    
    def post(self, request, pk):
        try:
            property = Property.objects.get(pk=pk, owner=request.user)
        except Property.DoesNotExist:
            return Response(
                {'detail': 'Property not found.'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        images = request.FILES.getlist('images')
        image_urls = []
        
        for idx, image in enumerate(images):
            ext = image.name.split('.')[-1]
            filename = f"properties/{property.id}/{uuid.uuid4()}.{ext}"
            filepath = default_storage.save(filename, ContentFile(image.read()))
            url = default_storage.url(filepath)
            image_urls.append(url)
            
            PropertyImage.objects.create(
                property=property,
                image_url=url,
                order=idx
            )
        
        existing_images = property.images or []
        property.images = existing_images + image_urls
        property.save()
        
        return Response({
            'images': property.images,
            'uploaded': image_urls
        }, status=status.HTTP_200_OK)


class DeletePropertyImageView(APIView):
    """Delete a property image"""
    permission_classes = [permissions.IsAuthenticated]
    
    def delete(self, request, pk, image_id):
        try:
            property = Property.objects.get(pk=pk, owner=request.user)
            image = PropertyImage.objects.get(pk=image_id, property=property)
        except (Property.DoesNotExist, PropertyImage.DoesNotExist):
            return Response(
                {'detail': 'Property or image not found.'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        if image.image_url in property.images:
            property.images.remove(image.image_url)
            property.save()
        
        if image.image_url:
            default_storage.delete(image.image_url.replace('/media/', ''))
        image.delete()
        
        return Response(status=status.HTTP_204_NO_CONTENT)


class PropertySearchView(APIView):
    """Search published properties — tenant-facing endpoint.

    Filters are intentionally loose: the tenant form doesn't have to match
    the backend 1-to-1.  Missing / empty params are simply ignored.
    """
    permission_classes = [permissions.IsAuthenticated]

    # ── rental_type mapping from duration keywords → stored values ────────
    RENTAL_TYPE_MAP = {
        'short': 'short-term',
        'medium': 'short-term',   # 6 months treated as short-term
        'long':  'long-term',
    }

    def post(self, request):
        filters = request.data

        queryset = Property.objects.filter(is_published=True, status='published')

        # ── Location ──────────────────────────────────────────────────────
        city = filters.get('city', '').strip()
        if city:
            queryset = queryset.filter(city__icontains=city)

        state = filters.get('state', '').strip()
        if state:
            queryset = queryset.filter(state__icontains=state)

        # ── Property type (fuzzy match) ──────────────────────────────────
        prop_type = filters.get('propertyType', '').strip()
        if prop_type:
            queryset = queryset.filter(property_type__icontains=prop_type)

        # ── Price range ───────────────────────────────────────────────────
        min_price = filters.get('minPrice')
        max_price = filters.get('maxPrice')
        if min_price:
            queryset = queryset.filter(price_amount__gte=min_price)
        if max_price:
            queryset = queryset.filter(price_amount__lte=max_price)

        # ── Bedrooms / Bathrooms ──────────────────────────────────────────
        bedrooms = filters.get('bedrooms')
        if bedrooms:
            queryset = queryset.filter(bedrooms__gte=int(bedrooms))
        bathrooms = filters.get('bathrooms')
        if bathrooms:
            queryset = queryset.filter(bathrooms__gte=int(bathrooms))

        # ── Amenities → soft preference (no hard filter) ──────────────────
        # Amenities are NOT used to filter out properties.
        # The search returns all published properties in the area regardless.

        # ── Duration → rental_type ────────────────────────────────────────
        duration = filters.get('duration', '').strip()
        rental_type = filters.get('rentalType', '').strip()
        if rental_type:
            queryset = queryset.filter(rental_type__iexact=rental_type)
        elif duration:
            mapped = self.RENTAL_TYPE_MAP.get(duration.lower())
            if mapped:
                queryset = queryset.filter(rental_type__iexact=mapped)

        # ── Move-in date → available_from must be on or before ────────────
        move_in = filters.get('moveInDate', '').strip()
        if move_in:
            try:
                from datetime import date as _date
                parsed = _date.fromisoformat(move_in)
                queryset = queryset.filter(available_from__lte=parsed)
            except (ValueError, TypeError):
                pass  # ignore malformed date

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