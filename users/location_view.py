"""
users/location_view.py

Two endpoints:
  POST /api/users/location/         — save GPS coordinates (user granted permission)
  POST /api/users/location/detect/  — detect location from IP + timezone (GPS denied)
"""

from rest_framework import serializers
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.contrib.gis.geos import Point

from utils.location_detect import resolve_location, get_client_ip


# ─── Serializers ──────────────────────────────────────────────────────────────

class GPSLocationSerializer(serializers.Serializer):
    latitude  = serializers.FloatField(min_value=-90,  max_value=90)
    longitude = serializers.FloatField(min_value=-180, max_value=180)


class DetectLocationSerializer(serializers.Serializer):
    # Frontend sends the browser's timezone string
    # e.g. Intl.DateTimeFormat().resolvedOptions().timeZone → "Africa/Lagos"
    timezone = serializers.CharField(max_length=100, required=False, default='')


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _save_location_and_notify(user, latitude, longitude, source, city='', country=''):
    """Saves PostGIS Point to user, fires WebSocket event."""
    user.location        = Point(longitude, latitude, srid=4326)  # Point(x=lon, y=lat)
    user.location_source = source
    if city and not user.city:
        user.city = city
    if country and not user.current_country:
        user.current_country = country

    update_fields = ['location', 'location_source']
    if city and not user.city:
        update_fields.append('city')
    if country and not user.current_country:
        update_fields.append('current_country')

    user.save(update_fields=update_fields)

    # Notify frontend via WebSocket → triggers shop feed refresh
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


# ─── Views ────────────────────────────────────────────────────────────────────

class UpdateLocationView(APIView):
    """
    POST /api/users/location/
    Body: { "latitude": 6.5244, "longitude": 3.3792 }

    Called when user grants GPS permission in the browser/app.
    Most accurate source — saved with source='gps'.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = GPSLocationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        lat = serializer.validated_data['latitude']
        lon = serializer.validated_data['longitude']

        _save_location_and_notify(request.user, lat, lon, source='gps')

        return Response({
            'detail':    'Location updated via GPS.',
            'latitude':  lat,
            'longitude': lon,
            'source':    'gps',
        })


class DetectLocationView(APIView):
    """
    POST /api/users/location/detect/
    Body: { "timezone": "Africa/Lagos" }   ← from Intl.DateTimeFormat().resolvedOptions().timeZone

    Called when user DENIES GPS permission.
    Tries IP geolocation first, falls back to timezone signal.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = DetectLocationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        ip       = get_client_ip(request)
        timezone = serializer.validated_data.get('timezone', '')

        result = resolve_location(ip, timezone)

        if not result:
            return Response(
                {'detail': 'Could not determine location automatically. Please enter your city manually.'},
                status=400
            )

        _save_location_and_notify(
            request.user,
            result['latitude'],
            result['longitude'],
            source  = result['source'],
            city    = result.get('city', ''),
            country = result.get('country', ''),
        )

        return Response({
            'detail':    f"Location detected via {result['source']}.",
            'latitude':  result['latitude'],
            'longitude': result['longitude'],
            'city':      result.get('city', ''),
            'country':   result.get('country', ''),
            'source':    result['source'],
        })