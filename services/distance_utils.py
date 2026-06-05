import requests
import logging
from math import radians, sin, cos, sqrt, atan2
from django.conf import settings

logger = logging.getLogger(__name__)

# OSRM public instance (free, no API key needed)
# Rate limited but good for moderate usage
OSRM_BASE_URL = "http://router.project-osrm.org"

# Fallback: GraphHopper (requires free API key but more reliable)
# Sign up at https://www.graphhopper.com/ for a free API key (1000 requests/day)
GRAPH_HOPPER_BASE_URL = "https://graphhopper.com/api/1"
GRAPH_HOPPER_API_KEY = getattr(settings, 'GRAPH_HOPPER_API_KEY', None)


def get_coordinates_from_address(address, city, country_code):
    """
    Geocode an address to coordinates using Nominatim (OpenStreetMap's geocoder)
    Returns (lat, lon) or None if not found
    """
    try:
        # Build full address string
        full_address = f"{address}, {city}, {country_code}"
        
        # Nominatim API (free, requires User-Agent)
        url = "https://nominatim.openstreetmap.org/search"
        params = {
            'q': full_address,
            'format': 'json',
            'limit': 1,
        }
        headers = {
            'User-Agent': 'YourAppName/1.0 (your-email@example.com)'
        }
        
        response = requests.get(url, params=params, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if data:
                lat = float(data[0]['lat'])
                lon = float(data[0]['lon'])
                return lat, lon
        else:
            logger.warning(f"Geocoding failed for {full_address}: {response.status_code}")
            
    except Exception as e:
        logger.error(f"Geocoding error: {str(e)}")
    
    return None


def geocode_airport(airport_name, city, country_code):
    """
    Special geocoding for airports
    Returns (lat, lon) or None if not found
    """
    try:
        # Try with airport-specific query
        full_address = f"{airport_name} Airport, {city}, {country_code}"
        
        url = "https://nominatim.openstreetmap.org/search"
        params = {
            'q': full_address,
            'format': 'json',
            'limit': 1,
        }
        headers = {
            'User-Agent': 'YourAppName/1.0 (your-email@example.com)'
        }
        
        response = requests.get(url, params=params, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if data:
                lat = float(data[0]['lat'])
                lon = float(data[0]['lon'])
                return lat, lon
    except Exception as e:
        logger.error(f"Airport geocoding error: {str(e)}")
    
    return None


def calculate_distance_osrm(start_coords, end_coords):
    """
    Calculate driving distance between two coordinates using OSRM
    Returns distance in kilometers, duration in seconds
    """
    try:
        # Format coordinates for OSRM: lon,lat;lon,lat
        coordinates = f"{start_coords[1]},{start_coords[0]};{end_coords[1]},{end_coords[0]}"
        url = f"{OSRM_BASE_URL}/route/v1/driving/{coordinates}"
        params = {
            'overview': 'false',
            'steps': 'false'
        }
        
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if data.get('code') == 'Ok' and data.get('routes'):
                route = data['routes'][0]
                distance_km = route['distance'] / 1000  # Convert meters to km
                duration_sec = route['duration']
                
                return {
                    'distance_km': round(distance_km, 2),
                    'duration_min': round(duration_sec / 60, 2),
                    'duration_sec': duration_sec
                }
        else:
            logger.warning(f"OSRM failed: {response.status_code}")
            
    except Exception as e:
        logger.error(f"OSRM error: {str(e)}")
    
    return None


def calculate_distance_graphhopper(start_coords, end_coords):
    """
    Calculate driving distance using GraphHopper (requires API key)
    Returns distance in kilometers, duration in seconds
    """
    if not GRAPH_HOPPER_API_KEY:
        return None
    
    try:
        url = f"{GRAPH_HOPPER_BASE_URL}/route"
        params = {
            'point': [f"{start_coords[0]},{start_coords[1]}", f"{end_coords[0]},{end_coords[1]}"],
            'vehicle': 'car',
            'key': GRAPH_HOPPER_API_KEY,
            'locale': 'en',
            'points_encoded': 'false',
            'calc_points': 'false'
        }
        
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if data.get('paths'):
                path = data['paths'][0]
                distance_km = path['distance'] / 1000
                duration_sec = path['time'] / 1000
                
                return {
                    'distance_km': round(distance_km, 2),
                    'duration_min': round(duration_sec / 60, 2),
                    'duration_sec': duration_sec
                }
        else:
            logger.warning(f"GraphHopper failed: {response.status_code}")
            
    except Exception as e:
        logger.error(f"GraphHopper error: {str(e)}")
    
    return None


def haversine_distance(coord1, coord2):
    """
    Calculate straight-line (great-circle) distance between two coordinates
    Used as fallback when routing APIs fail
    """
    lat1, lon1 = coord1
    lat2, lon2 = coord2
    
    R = 6371  # Earth's radius in kilometers
    
    lat1_rad = radians(lat1)
    lat2_rad = radians(lat2)
    delta_lat = radians(lat2 - lat1)
    delta_lon = radians(lon2 - lon1)
    
    a = sin(delta_lat / 2) ** 2 + cos(lat1_rad) * cos(lat2_rad) * sin(delta_lon / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    
    distance_km = R * c
    
    # Rough estimate: average driving speed ~40 km/h in city
    duration_hours = distance_km / 40
    duration_min = duration_hours * 60
    
    return {
        'distance_km': round(distance_km, 2),
        'duration_min': round(duration_min, 2),
        'distance_type': 'straight_line'
    }


def calculate_distance_between_addresses(pickup_address, pickup_city, pickup_country,
                                        arrival_address, arrival_city, arrival_country):
    """
    Main function to calculate distance between pickup and arrival points
    Tries OSRM first, falls back to GraphHopper, then Haversine
    """
    # Get coordinates for both addresses
    pickup_coords = get_coordinates_from_address(pickup_address, pickup_city, pickup_country)
    arrival_coords = get_coordinates_from_address(arrival_address, arrival_city, arrival_country)
    
    if not pickup_coords or not arrival_coords:
        logger.warning("Could not geocode one or both addresses")
        return None
    
    # Try OSRM first (free, no API key)
    result = calculate_distance_osrm(pickup_coords, arrival_coords)
    
    # If OSRM fails, try GraphHopper if available
    if not result and GRAPH_HOPPER_API_KEY:
        result = calculate_distance_graphhopper(pickup_coords, arrival_coords)
    
    # If both routing APIs fail, use straight-line distance as fallback
    if not result:
        logger.info("Using Haversine fallback for distance calculation")
        result = haversine_distance(pickup_coords, arrival_coords)
        result['distance_type'] = 'straight_line'
    else:
        result['distance_type'] = 'routing'
    
    # Add coordinates to result for debugging
    result['pickup_coords'] = pickup_coords
    result['arrival_coords'] = arrival_coords
    
    return result


def calculate_price_based_on_distance(base_price, distance_km, price_per_km=2.0):
    """
    Calculate dynamic pricing based on distance
    Example: base_price + (distance_km * price_per_km)
    """
    return round(base_price + (distance_km * price_per_km), 2)


def calculate_distance_between_coordinates(lat1, lon1, lat2, lon2):
    """
    Calculate distance between two coordinates using Haversine formula
    Useful for quick calculations without API calls
    """
    coord1 = (lat1, lon1)
    coord2 = (lat2, lon2)
    return haversine_distance(coord1, coord2)


def get_nearest_driver(pickup_lat, pickup_lon, drivers, max_distance_km=50):
    """
    Find the nearest driver to a pickup location
    
    Args:
        pickup_lat, pickup_lon: Coordinates of pickup location
        drivers: List of driver objects with lat/lon attributes
        max_distance_km: Maximum distance to consider
    
    Returns:
        The nearest driver or None if none within max_distance_km
    """
    nearest_driver = None
    min_distance = float('inf')
    
    for driver in drivers:
        if hasattr(driver, 'current_lat') and hasattr(driver, 'current_lon'):
            distance_data = haversine_distance(
                (pickup_lat, pickup_lon),
                (driver.current_lat, driver.current_lon)
            )
            distance = distance_data['distance_km']
            
            if distance < min_distance and distance <= max_distance_km:
                min_distance = distance
                nearest_driver = driver
    
    return nearest_driver


def calculate_eta_from_distance(distance_km, traffic_factor=1.0):
    """
    Calculate ETA based on distance and traffic conditions
    
    Args:
        distance_km: Distance in kilometers
        traffic_factor: 1.0 = normal, >1.0 = heavy traffic, <1.0 = light traffic
    
    Returns:
        Estimated time in minutes
    """
    # Average speed assumption: 30 km/h in city traffic
    avg_speed_kmh = 30 * traffic_factor
    eta_hours = distance_km / avg_speed_kmh
    eta_minutes = eta_hours * 60
    
    return round(eta_minutes, 2)