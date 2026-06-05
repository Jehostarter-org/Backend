"""
GET /api/location-search/?q=<query>

Proxies OpenStreetMap Nominatim for free address autocomplete.
No API key required. Returns results in the shape the frontend expects:
  { "results": ["Address 1", "Address 2", ...] }
"""

import requests
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny


class LocationSearchView(APIView):
    """
    Proxy to Nominatim so the frontend can do address autocomplete
    without needing a Google Places API key.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        q = request.query_params.get('q', '').strip()

        if len(q) < 3:
            return Response({'results': []})

        try:
            resp = requests.get(
                'https://nominatim.openstreetmap.org/search',
                params={
                    'q':              q,
                    'format':         'json',
                    'addressdetails': 0,
                    'limit':          8,
                },
                headers={
                    # Nominatim requires a non-empty User-Agent
                    'User-Agent': 'Jehostarter/1.0 (contact@jehostarter.com)',
                },
                timeout=5,
            )
            resp.raise_for_status()
            data = resp.json()
            results = [item.get('display_name', '') for item in data if item.get('display_name')]
            return Response({'results': results})

        except Exception:
            return Response({'results': []})
