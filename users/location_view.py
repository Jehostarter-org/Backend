from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.contrib.gis.geos import Point
import requests


def get_ip(request):
    x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded:
        return x_forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


class UpdateLocationView(APIView):
    """POST /api/users/location/ -- save GPS coordinates from frontend."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        lat    = request.data.get('latitude')
        lng    = request.data.get('longitude')
        source = request.data.get('source', 'gps')
        country_code = request.data.get('country_code')
        city = request.data.get('city')

        if lat is None or lng is None:
            return Response({'error': 'latitude and longitude required'}, status=400)

        try:
            request.user.location        = Point(float(lng), float(lat), srid=4326)
            request.user.location_source = source
            update_fields = ['location', 'location_source']

            if country_code:
                request.user.current_country = country_code
                update_fields.append('current_country')

            if city:
                request.user.city = city
                update_fields.append('city')

            request.user.save(update_fields=update_fields)
            return Response({
                'status': 'location updated',
                'lat':    float(lat),
                'lng':    float(lng),
                'source': source,
            })
        except Exception as e:
            return Response({'error': str(e)}, status=400)


class DetectLocationView(APIView):
    """GET /api/users/location/detect/ -- detect location from IP address."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        ip = get_ip(request)

        # Localhost fallback for development
        if ip in ('127.0.0.1', '::1', 'localhost'):
            ip = None

        try:
            if ip:
                res = requests.get(
                    f'http://ip-api.com/json/{ip}?fields=status,lat,lon,city,countryCode',
                    timeout=5
                )
            else:
                res = requests.get(
                    'http://ip-api.com/json/?fields=status,lat,lon,city,countryCode',
                    timeout=5
                )

            data = res.json()

            if data.get('status') == 'success':
                lat          = data['lat']
                lng          = data['lon']
                city         = data.get('city', '')
                country_code = data.get('countryCode', '')

                request.user.location        = Point(float(lng), float(lat), srid=4326)
                request.user.location_source = 'ip'
                request.user.current_country = country_code
                request.user.city            = city
                request.user.save(update_fields=['location', 'location_source', 'current_country', 'city'])

                return Response({
                    'status':       'ok',
                    'lat':          lat,
                    'lng':          lng,
                    'city':         city,
                    'country_code': country_code,
                    'source':       'ip',
                })

        except Exception:
            pass

        return Response({'status': 'failed', 'error': 'Could not detect location'}, status=200)