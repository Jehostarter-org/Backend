"""
users/graphql.py

GraphQL mutation + query for location (PostGIS version).
Merge LocationMutations and LocationQueries into your existing Mutation/Query classes.
"""

import strawberry
from strawberry.types import Info
from typing import Optional
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.contrib.gis.geos import Point
from django.contrib.gis.measure import D
from django.contrib.gis.db.models.functions import Distance

from shops.models import Shop
from utils.location_detect import resolve_location, get_client_ip


# ─── Response types ───────────────────────────────────────────────────────────

@strawberry.type
class LocationResult:
    latitude:  float
    longitude: float
    city:      str
    country:   str
    source:    str   # gps | ip | timezone


# ─── Mutations ────────────────────────────────────────────────────────────────

@strawberry.type
class LocationMutations:

    @strawberry.mutation
    def update_location(
        self,
        info: Info,
        latitude:  float,
        longitude: float,
    ) -> str:
        """
        Save GPS coordinates granted by the user.

        mutation {
          updateLocation(latitude: 6.5244, longitude: 3.3792)
        }
        """
        request = info.context["request"]
        user    = request.user
        if not user.is_authenticated:
            raise Exception("Authentication required.")

        user.location        = Point(longitude, latitude, srid=4326)
        user.location_source = 'gps'
        user.save(update_fields=['location', 'location_source'])

        _fire_location_ws(user, latitude, longitude, 'gps')
        return "Location updated."

    @strawberry.mutation
    def detect_location(
        self,
        info: Info,
        timezone: Optional[str] = '',
    ) -> Optional[LocationResult]:
        """
        Detect location from IP + timezone when GPS is denied.

        mutation {
          detectLocation(timezone: "Africa/Lagos") {
            latitude longitude city country source
          }
        }
        """
        request = info.context["request"]
        user    = request.user
        if not user.is_authenticated:
            raise Exception("Authentication required.")

        ip     = get_client_ip(request)
        result = resolve_location(ip, timezone or '')

        if not result:
            return None

        user.location        = Point(result['longitude'], result['latitude'], srid=4326)
        user.location_source = result['source']
        if result.get('city') and not user.city:
            user.city = result['city']
        if result.get('country') and not user.current_country:
            user.current_country = result['country']
        user.save(update_fields=['location', 'location_source', 'city', 'current_country'])

        _fire_location_ws(user, result['latitude'], result['longitude'], result['source'])

        return LocationResult(
            latitude  = result['latitude'],
            longitude = result['longitude'],
            city      = result.get('city', ''),
            country   = result.get('country', ''),
            source    = result['source'],
        )


# ─── Queries ──────────────────────────────────────────────────────────────────

@strawberry.type
class LocationQueries:

    @strawberry.field
    def nearby_shops(
        self,
        info: Info,
        latitude:  Optional[float] = None,
        longitude: Optional[float] = None,
        radius_km: Optional[float] = 50.0,
    ) -> list:
        """
        Returns shops within radius_km of given (or user's stored) coordinates.
        Uses PostGIS ST_DWithin — single indexed DB query.

        query {
          nearbyShops(latitude: 6.5244, longitude: 3.3792, radiusKm: 30) {
            id name city latitude longitude
          }
        }
        """
        request = info.context["request"]
        user    = request.user if request.user.is_authenticated else None

        # Resolve point: explicit args → stored user location → None
        if latitude is not None and longitude is not None:
            point = Point(longitude, latitude, srid=4326)
        elif user and user.location:
            point = user.location
        else:
            point = None

        base_qs = Shop.objects.filter(is_active=True)

        if point:
            return list(
                base_qs.filter(
                    location__dwithin=(point, D(km=radius_km))
                ).annotate(
                    distance=Distance('location', point)
                ).order_by('distance')
            )

        # Fallback: country filter
        if user:
            countries = [c for c in [user.current_country, user.destination_country] if c]
            if countries:
                return list(base_qs.filter(country_code__in=countries))

        return list(base_qs)


# ─── Helper ───────────────────────────────────────────────────────────────────

def _fire_location_ws(user, latitude, longitude, source):
    """Pushes location.updated event to user's WebSocket channel."""
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        f'user_{user.id}',
        {
            'type':      'location.updated',
            'latitude':  str(latitude),
            'longitude': str(longitude),
            'source':    source,
        }
    )