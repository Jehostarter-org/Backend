"""
utils/location_detect.py

Detects a user's location when GPS is denied, using:
  1. IP geolocation  (ip-api.com — free, no API key needed, 45 req/min)
  2. Timezone signal (narrows down region if IP geolocation fails)

Returns a dict:
  {
    "latitude":  float,
    "longitude": float,
    "city":      str,
    "country":   str,   # ISO 2-letter code
    "source":    "ip" | "timezone",
  }
  or None if all methods fail.
"""

import requests
import pytz
from timezonefinder import TimezoneFinder


# ─── IP Geolocation ───────────────────────────────────────────────────────────

def detect_from_ip(ip_address: str) -> dict | None:
    """
    Uses ip-api.com to resolve an IP to coordinates + city + country.
    Free tier: 45 requests/minute, no API key required.
    Falls back gracefully if the request fails or IP is private.
    """
    if not ip_address or ip_address in ('127.0.0.1', '::1', 'localhost'):
        return None

    try:
        resp = requests.get(
            f'http://ip-api.com/json/{ip_address}',
            params={'fields': 'status,lat,lon,city,countryCode'},
            timeout=3,
        )
        data = resp.json()

        if data.get('status') != 'success':
            return None

        return {
            'latitude':  data['lat'],
            'longitude': data['lon'],
            'city':      data.get('city', ''),
            'country':   data.get('countryCode', ''),
            'source':    'ip',
        }

    except Exception:
        return None


# ─── Timezone Signal ──────────────────────────────────────────────────────────

# Maps IANA timezone → approximate city centre coordinates + country.
# Covers the most common timezones your migrant users will be in.
TIMEZONE_COORDS = {
    # Africa
    'Africa/Lagos':       (6.5244,   3.3792,  'NG', 'Lagos'),
    'Africa/Abuja':       (9.0765,   7.3986,  'NG', 'Abuja'),
    'Africa/Nairobi':     (-1.2864,  36.8172, 'KE', 'Nairobi'),
    'Africa/Accra':       (5.6037,   -0.1870, 'GH', 'Accra'),
    'Africa/Johannesburg':(- 26.2041, 28.0473,'ZA', 'Johannesburg'),
    'Africa/Cairo':       (30.0444,  31.2357, 'EG', 'Cairo'),

    # Europe
    'Europe/London':      (51.5074,  -0.1278, 'GB', 'London'),
    'Europe/Paris':       (48.8566,   2.3522, 'FR', 'Paris'),
    'Europe/Berlin':      (52.5200,  13.4050, 'DE', 'Berlin'),
    'Europe/Amsterdam':   (52.3676,   4.9041, 'NL', 'Amsterdam'),
    'Europe/Dublin':      (53.3498,  -6.2603, 'IE', 'Dublin'),
    'Europe/Lisbon':      (38.7169,  -9.1399, 'PT', 'Lisbon'),

    # North America
    'America/New_York':   (40.7128,  -74.0060,'US', 'New York'),
    'America/Chicago':    (41.8781,  -87.6298,'US', 'Chicago'),
    'America/Los_Angeles':(34.0522, -118.2437,'US', 'Los Angeles'),
    'America/Toronto':    (43.6510,  -79.3470,'CA', 'Toronto'),
    'America/Vancouver':  (49.2827, -123.1207,'CA', 'Vancouver'),

    # Asia Pacific
    'Asia/Dubai':         (25.2048,  55.2708, 'AE', 'Dubai'),
    'Asia/Riyadh':        (24.7136,  46.6753, 'SA', 'Riyadh'),
    'Australia/Sydney':   (-33.8688, 151.2093,'AU', 'Sydney'),
    'Australia/Melbourne':(-37.8136, 144.9631,'AU', 'Melbourne'),
    'Asia/Singapore':     (1.3521,   103.8198,'SG', 'Singapore'),
    'Asia/Kolkata':       (28.6139,  77.2090, 'IN', 'New Delhi'),
}


def detect_from_timezone(timezone_str: str) -> dict | None:
    """
    Uses the client-supplied timezone string (e.g. 'Africa/Lagos') to
    return approximate coordinates for that timezone's main city.
    Less precise than GPS or IP but works completely offline.
    """
    if not timezone_str:
        return None

    coords = TIMEZONE_COORDS.get(timezone_str)
    if coords:
        lat, lon, country, city = coords
        return {
            'latitude':  lat,
            'longitude': lon,
            'city':      city,
            'country':   country,
            'source':    'timezone',
        }

    # Try to derive country from timezone string (e.g. "Africa/Lagos" → "Africa")
    # as a last resort for unknown timezones
    try:
        tz   = pytz.timezone(timezone_str)
        tf   = TimezoneFinder()
        # Use TimezoneFinder to get a coordinate for this timezone
        lat, lon = tf.timezone_at_land(None, None) or (None, None)
        if lat and lon:
            return {
                'latitude':  lat,
                'longitude': lon,
                'city':      '',
                'country':   '',
                'source':    'timezone',
            }
    except Exception:
        pass

    return None


# ─── Main resolver ────────────────────────────────────────────────────────────

def resolve_location(ip_address: str, timezone_str: str = '') -> dict | None:
    """
    Tries location detection methods in order of accuracy:
      1. IP geolocation
      2. Timezone detection

    Returns the first successful result, or None if all fail.
    """
    result = detect_from_ip(ip_address)
    if result:
        return result

    result = detect_from_timezone(timezone_str)
    if result:
        return result

    return None


def get_client_ip(request) -> str:
    """
    Extracts the real client IP from the Django request.
    Handles proxies and load balancers (X-Forwarded-For header).
    """
    x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded:
        # X-Forwarded-For can be a comma-separated list; first is the real client
        return x_forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '')