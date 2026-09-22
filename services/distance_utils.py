import requests
import logging
from math import radians, sin, cos, sqrt, atan2
from django.conf import settings

logger = logging.getLogger(__name__)

# OpenRouteService (ORS) — free tier: 2,000 requests/day
# Sign up at https://openrouteservice.org/dev/#/home to get your key
# Add ORS_API_KEY to your .env and settings.py
ORS_BASE_URL = "https://api.openrouteservice.org"
ORS_API_KEY = getattr(settings, 'ORS_API_KEY', None)

# Nominatim (OpenStreetMap geocoder) — free, no API key needed
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
# Required by Nominatim ToS — replace with your app name and contact email
NOMINATIM_USER_AGENT = getattr(
    settings,
    'NOMINATIM_USER_AGENT',
    'Jehostarter/1.0 (contact@jehostarter.com)'
)


def get_coordinates_from_address(address, city, country_code):
    """
    Geocode an address to (lat, lon) using OpenRouteService Pelias geocoder.
    Falls back to Nominatim if ORS key is unavailable.
    city is optional — geocoding works with just address + country.
    Returns (lat, lon) or None if not found.
    """
    # Build query string — filter out empty parts to avoid double commas
    query_parts = [p for p in [address, city, country_code] if p]
    full_query = ", ".join(query_parts)

    # ── Try ORS geocoding first (more accurate, structured) ──────────────
    if ORS_API_KEY:
        try:
            url = f"{ORS_BASE_URL}/geocode/search"
            response = requests.get(
                url,
                params={
                    "api_key": ORS_API_KEY,
                    "text": full_query,
                    "size": 1,
                },
                timeout=10,
            )
            if response.status_code == 200:
                features = response.json().get("features", [])
                if features:
                    lon, lat = features[0]["geometry"]["coordinates"]
                    return float(lat), float(lon)
            else:
                logger.warning("ORS geocoding failed (%s): %s", response.status_code, response.text)
        except Exception as exc:
            logger.error("ORS geocoding error: %s", exc)

    # ── Fallback: Nominatim ───────────────────────────────────────────────
    try:
        response = requests.get(
            NOMINATIM_URL,
            params={"q": full_query, "format": "json", "limit": 1},
            headers={"User-Agent": NOMINATIM_USER_AGENT},
            timeout=10,
        )
        if response.status_code == 200:
            data = response.json()
            if data:
                return float(data[0]["lat"]), float(data[0]["lon"])
        else:
            logger.warning("Nominatim geocoding failed (%s) for: %s", response.status_code, full_query)
    except Exception as exc:
        logger.error("Nominatim geocoding error: %s", exc)

    return None


def geocode_airport(airport_name, city, country_code):
    """
    Geocode an airport to (lat, lon).
    Tries ORS first, falls back to Nominatim.
    Returns (lat, lon) or None if not found.
    """
    query = f"{airport_name} Airport, {city}, {country_code}"

    # ── Try ORS ──────────────────────────────────────────────────────────
    if ORS_API_KEY:
        try:
            url = f"{ORS_BASE_URL}/geocode/search"
            response = requests.get(
                url,
                params={
                    "api_key": ORS_API_KEY,
                    "text": query,
                    "size": 1,
                    "layers": "venue,address",
                },
                timeout=10,
            )
            if response.status_code == 200:
                features = response.json().get("features", [])
                if features:
                    lon, lat = features[0]["geometry"]["coordinates"]
                    return float(lat), float(lon)
        except Exception as exc:
            logger.error("ORS airport geocoding error: %s", exc)

    # ── Fallback: Nominatim ───────────────────────────────────────────────
    try:
        response = requests.get(
            NOMINATIM_URL,
            params={"q": query, "format": "json", "limit": 1},
            headers={"User-Agent": NOMINATIM_USER_AGENT},
            timeout=10,
        )
        if response.status_code == 200:
            data = response.json()
            if data:
                return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception as exc:
        logger.error("Nominatim airport geocoding error: %s", exc)

    return None


def calculate_distance_osrm(start_coords, end_coords):
    """
    Calculate driving distance and duration using OpenRouteService Directions API.
    Function name kept as-is so views.py requires no changes.
    Returns dict with distance_km, duration_min, duration_sec — or None on failure.
    """
    if not ORS_API_KEY:
        logger.warning("ORS_API_KEY not set — skipping ORS routing")
        return None

    try:
        url = f"{ORS_BASE_URL}/v2/directions/driving-car"
        # ORS expects [longitude, latitude] order
        payload = {
            "coordinates": [
                [start_coords[1], start_coords[0]],
                [end_coords[1], end_coords[0]],
            ]
        }
        headers = {
            "Authorization": ORS_API_KEY,
            "Content-Type": "application/json",
        }

        response = requests.post(url, json=payload, headers=headers, timeout=10)

        if response.status_code == 200:
            data = response.json()
            routes = data.get("routes", [])
            if routes:
                summary = routes[0]["summary"]
                distance_km = summary["distance"] / 1000  # metres → km
                duration_sec = summary["duration"]
                return {
                    "distance_km": round(distance_km, 2),
                    "duration_min": round(duration_sec / 60, 2),
                    "duration_sec": duration_sec,
                }
        else:
            logger.warning("ORS directions failed (%s): %s", response.status_code, response.text)

    except Exception as exc:
        logger.error("ORS directions error: %s", exc)

    return None


GRAPH_HOPPER_BASE = "https://graphhopper.com/api/1"

def calculate_distance_graphhopper(start_coords, end_coords):
    """
    Calculate driving distance using GraphHopper Routing API.
    Used as fallback when ORS routing fails or has no key.
    Returns dict with distance_km, duration_min, duration_sec — or None on failure.
    """
    gh_key = getattr(settings, 'GRAPH_HOPPER_API_KEY', None)
    if not gh_key:
        logger.warning("GRAPH_HOPPER_API_KEY not set — skipping GraphHopper routing")
        return None

    try:
        url = f"{GRAPH_HOPPER_BASE}/route"
        # GraphHopper expects [lat, lon] order
        params = {
            "point": [f"{start_coords[0]},{start_coords[1]}", f"{end_coords[0]},{end_coords[1]}"],
            "vehicle": "car",
            "locale": "en",
            "key": gh_key,
            "type": "json",
        }
        response = requests.get(url, params=params, timeout=10)

        if response.status_code == 200:
            data = response.json()
            paths = data.get("paths", [])
            if paths:
                distance_km = paths[0]["distance"] / 1000
                duration_sec = paths[0]["time"] / 1000
                return {
                    "distance_km": round(distance_km, 2),
                    "duration_min": round(duration_sec / 60, 2),
                    "duration_sec": duration_sec,
                }
        else:
            logger.warning("GraphHopper routing failed (%s): %s", response.status_code, response.text)

    except Exception as exc:
        logger.error("GraphHopper routing error: %s", exc)

    return None


def haversine_distance(coord1, coord2):
    """
    Straight-line (great-circle) distance between two (lat, lon) pairs.
    Used as last-resort fallback when all routing APIs fail.
    Returns dict with distance_km, duration_min, distance_type.
    """
    lat1, lon1 = coord1
    lat2, lon2 = coord2

    R = 6371  # Earth radius in km

    d_lat = radians(lat2 - lat1)
    d_lon = radians(lon2 - lon1)
    a = (
        sin(d_lat / 2) ** 2
        + cos(radians(lat1)) * cos(radians(lat2)) * sin(d_lon / 2) ** 2
    )
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    distance_km = R * c

    # Conservative city-speed estimate: 40 km/h
    duration_min = (distance_km / 40) * 60

    return {
        "distance_km": round(distance_km, 2),
        "duration_min": round(duration_min, 2),
        "distance_type": "straight_line",
    }


def _route_ors(start_coords, end_coords):
    """
    Full driving route geometry from OpenRouteService.
    Returns dict with coordinates (list of [lat, lng] points), distance_km,
    duration_min, distance_type — or None on failure.
    """
    if not ORS_API_KEY:
        logger.warning("ORS_API_KEY not set — skipping ORS route")
        return None

    try:
        url = f"{ORS_BASE_URL}/v2/directions/driving-car"
        # ORS expects [longitude, latitude] order; geometry_format=geojson
        # returns the polyline as GeoJSON so we can draw it on the map.
        payload = {
            "coordinates": [
                [start_coords[1], start_coords[0]],
                [end_coords[1], end_coords[0]],
            ],
            "geometry_format": "geojson",
        }
        headers = {
            "Authorization": ORS_API_KEY,
            "Content-Type": "application/json",
        }

        response = requests.post(url, json=payload, headers=headers, timeout=15)

        if response.status_code == 200:
            routes = response.json().get("routes", [])
            if routes:
                route = routes[0]
                summary = route["summary"]
                coords = route["geometry"]["coordinates"]  # [[lon, lat], ...]
                return {
                    "coordinates": [[float(lat), float(lng)] for lng, lat in coords],
                    "distance_km": round(summary["distance"] / 1000, 2),
                    "duration_min": round(summary["duration"] / 60, 2),
                    "distance_type": "routing",
                }
        else:
            logger.warning("ORS route failed (%s): %s", response.status_code, response.text)
    except Exception as exc:
        logger.error("ORS route error: %s", exc)

    return None


def _route_graphhopper(start_coords, end_coords):
    """
    Full driving route geometry from GraphHopper (fallback when ORS fails).
    Returns dict with coordinates (list of [lat, lng] points), distance_km,
    duration_min, distance_type — or None on failure.
    """
    gh_key = getattr(settings, 'GRAPH_HOPPER_API_KEY', None)
    if not gh_key:
        logger.warning("GRAPH_HOPPER_API_KEY not set — skipping GraphHopper route")
        return None

    try:
        url = f"{GRAPH_HOPPER_BASE}/route"
        # points_encoded=false returns GeoJSON coordinates so we can draw them.
        params = {
            "point": [f"{start_coords[0]},{start_coords[1]}", f"{end_coords[0]},{end_coords[1]}"],
            "vehicle": "car",
            "locale": "en",
            "key": gh_key,
            "type": "json",
            "points_encoded": "false",
        }
        response = requests.get(url, params=params, timeout=15)

        if response.status_code == 200:
            paths = response.json().get("paths", [])
            if paths:
                path = paths[0]
                coords = path["points"]["coordinates"]  # [[lon, lat], ...]
                return {
                    "coordinates": [[float(lat), float(lng)] for lng, lat in coords],
                    "distance_km": round(path["distance"] / 1000, 2),
                    "duration_min": round((path["time"] / 1000) / 60, 2),
                    "distance_type": "routing",
                }
        else:
            logger.warning("GraphHopper route failed (%s): %s", response.status_code, response.text)
    except Exception as exc:
        logger.error("GraphHopper route error: %s", exc)

    return None


def get_route_coordinates(start_coords, end_coords):
    """
    Driving route as a polyline of [lat, lng] points (Uber-style road route,
    not a straight line). Tries OpenRouteService, falls back to GraphHopper,
    then to a straight two-point line so the map still renders.
    Returns dict with coordinates, distance_km, duration_min, distance_type.
    """
    result = _route_ors(start_coords, end_coords)
    if not result:
        result = _route_graphhopper(start_coords, end_coords)

    if not result:
        logger.info("Routing unavailable — using straight-line fallback")
        haversine = haversine_distance(start_coords, end_coords)
        result = {
            "coordinates": [[start_coords[0], start_coords[1]], [end_coords[0], end_coords[1]]],
            "distance_km": haversine["distance_km"],
            "duration_min": haversine["duration_min"],
            "distance_type": "straight_line",
        }

    return result


def calculate_distance_from_coords(pickup_lat, pickup_lon, arrival_lat, arrival_lon):
    """
    Calculate driving distance from pre-geocoded coordinates.
    Used when the frontend already has lat/lon from autocomplete.
    Falls back to Haversine if ORS routing fails.
    Returns result dict with distance_km, duration_min, coords, distance_type.
    """
    pickup_coords = (pickup_lat, pickup_lon)
    arrival_coords = (arrival_lat, arrival_lon)

    result = calculate_distance_osrm(pickup_coords, arrival_coords)
    if not result:
        result = calculate_distance_graphhopper(pickup_coords, arrival_coords)

    if not result:
        logger.info("ORS/GraphHopper routing unavailable — using Haversine fallback")
        result = haversine_distance(pickup_coords, arrival_coords)
        result["distance_type"] = "straight_line"
    else:
        result["distance_type"] = "routing"

    result["pickup_coords"] = pickup_coords
    result["arrival_coords"] = arrival_coords

    return result


def calculate_distance_between_addresses(
    pickup_address, pickup_city, pickup_country,
    arrival_address, arrival_city, arrival_country,
):
    """
    Main function called by views.py.
    Geocodes both addresses then calculates driving distance via ORS.
    Falls back to Haversine if ORS is unavailable or fails.
    Returns result dict with distance_km, duration_min, pickup_coords,
    arrival_coords, distance_type — or None if geocoding fails entirely.
    """
    pickup_coords = get_coordinates_from_address(pickup_address, pickup_city, pickup_country)
    arrival_coords = get_coordinates_from_address(arrival_address, arrival_city, arrival_country)

    if not pickup_coords or not arrival_coords:
        logger.warning("Could not geocode one or both addresses")
        return None

    # ── Try ORS routing ───────────────────────────────────────────────────
    result = calculate_distance_osrm(pickup_coords, arrival_coords)
    if not result:
        result = calculate_distance_graphhopper(pickup_coords, arrival_coords)

    # ── Haversine fallback ────────────────────────────────────────────────
    if not result:
        logger.info("ORS/GraphHopper routing unavailable — using Haversine fallback")
        result = haversine_distance(pickup_coords, arrival_coords)
        result["distance_type"] = "straight_line"
    else:
        result["distance_type"] = "routing"

    result["pickup_coords"] = pickup_coords
    result["arrival_coords"] = arrival_coords

    return result


def calculate_price_based_on_distance(per_km_rate, distance_km, flag_drop_fee=0, min_fare=0):
    """
    Uber/Bolt-style fare:
      distance_charge = distance_km × per_km_rate
      total           = flag_drop_fee + distance_charge
      final           = max(total, min_fare)
    Returns (total, distance_charge, flag_drop_fee).
    """
    distance_charge = round(distance_km * per_km_rate, 2)
    total = round(flag_drop_fee + distance_charge, 2)
    if min_fare > 0 and total < min_fare:
        total = round(float(min_fare), 2)
    return total, distance_charge, flag_drop_fee


def calculate_distance_between_coordinates(lat1, lon1, lat2, lon2):
    """
    Quick Haversine distance between two coordinate pairs.
    No API call — useful for driver proximity checks.
    """
    return haversine_distance((lat1, lon1), (lat2, lon2))


def get_nearest_driver(pickup_lat, pickup_lon, drivers, max_distance_km=50):
    """
    Find the nearest active driver to a pickup location.
    Drivers must have current_lat and current_lon attributes.
    Returns the nearest driver object or None if none within max_distance_km.
    """
    nearest_driver = None
    min_distance = float("inf")

    for driver in drivers:
        if hasattr(driver, "current_lat") and hasattr(driver, "current_lon"):
            result = haversine_distance(
                (pickup_lat, pickup_lon),
                (driver.current_lat, driver.current_lon),
            )
            distance = result["distance_km"]
            if distance < min_distance and distance <= max_distance_km:
                min_distance = distance
                nearest_driver = driver

    return nearest_driver


def calculate_eta_from_distance(distance_km, traffic_factor=1.0):
    """
    Estimate arrival time in minutes.
    traffic_factor > 1.0 = heavy traffic, < 1.0 = light traffic.
    Base assumption: 30 km/h average city speed.
    """
    avg_speed = 30 / traffic_factor  # slower when traffic_factor > 1
    eta_minutes = (distance_km / avg_speed) * 60
    return round(eta_minutes, 2)