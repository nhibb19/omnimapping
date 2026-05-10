"""
Geographic Scoring Engine
Provides advanced geographic intelligence and multimodal logistics analysis.

Functions:
- calculate_distance(): Haversine distance between two coordinates
- find_nearest_rail_hub(): Identify closest rail infrastructure
- find_nearest_port(): Identify closest maritime access
- calculate_multimodal_score(): Composite logistics accessibility
- calculate_geographic_opportunity_score(): Region-based opportunity analysis
- get_geographic_intelligence(): Full geographic profile for a company
"""

import math
from geopy.distance import geodesic

# Major port cities and coordinates
MAJOR_PORTS = {
    "Los Angeles": (34.0522, -118.2437),
    "Long Beach": (33.7437, -118.1915),
    "Oakland": (37.7749, -122.2158),
    "San Francisco": (37.7749, -122.4194),
    "Seattle": (47.6062, -122.3321),
    "Portland": (45.5152, -122.6784),
    "Savannah": (32.0809, -81.0912),
    "Charleston": (32.7765, -79.9318),
    "Houston": (29.7604, -95.3698),
    "Mobile": (30.6954, -88.2398),
    "New Orleans": (29.9511, -90.2623),
    "Miami": (25.7617, -80.1918),
    "Jacksonville": (30.3322, -81.6557),
    "Baltimore": (39.2904, -76.6122),
    "New York": (40.7128, -74.0060),
    "Boston": (42.3601, -71.0589),
}

# Major metropolitan areas (population centers)
MAJOR_CITIES = {
    "New York": (40.7128, -74.0060, "Northeast"),
    "Los Angeles": (34.0522, -118.2437, "Pacific"),
    "Chicago": (41.8781, -87.6298, "Midwest"),
    "Dallas": (32.7767, -96.7970, "South-Central"),
    "Houston": (29.7604, -95.3698, "South-Central"),
    "Phoenix": (33.4484, -112.0742, "Southwest"),
    "Philadelphia": (39.9526, -75.1652, "Northeast"),
    "San Antonio": (29.4241, -98.4936, "South-Central"),
    "San Diego": (32.7157, -117.1611, "Pacific"),
    "San Francisco": (37.7749, -122.4194, "Pacific"),
    "Atlanta": (33.7490, -84.3880, "Southeast"),
    "Denver": (39.7392, -104.9903, "Mountain"),
    "Miami": (25.7617, -80.1918, "Southeast"),
    "Seattle": (47.6062, -122.3321, "Pacific"),
    "Boston": (42.3601, -71.0589, "Northeast"),
    "Pittsburgh": (40.4406, -79.9959, "Northeast"),
    "Cleveland": (41.4993, -81.6944, "Midwest"),
    "Detroit": (42.3314, -83.0458, "Midwest"),
    "Minneapolis": (44.9778, -93.2650, "Midwest"),
    "Memphis": (35.1495, -90.0490, "Southeast"),
    "Birmingham": (33.5186, -86.8104, "Southeast"),
    "Jacksonville": (30.3322, -81.6557, "Southeast"),
    "Kansas City": (39.0997, -94.5786, "Midwest"),
    "Louisville": (38.2098, -84.5588, "Southeast"),
    "Nashville": (36.1627, -86.7816, "Southeast"),
}

def calculate_distance(lat1, lon1, lat2, lon2):
    """
    Calculate distance between two coordinates using Haversine formula.
    Returns distance in miles.
    """
    try:
        coords_1 = (float(lat1), float(lon1))
        coords_2 = (float(lat2), float(lon2))
        distance_km = geodesic(coords_1, coords_2).kilometers
        return distance_km * 0.621371  # Convert to miles
    except (ValueError, TypeError):
        return None

def find_nearest_rail_hub(company, rail_infrastructure):
    """
    Find the nearest rail hub and calculate proximity score.
    Returns dict with hub info and distance.
    """
    try:
        company_lat = float(company.get('latitude'))
        company_lon = float(company.get('longitude'))
    except (ValueError, TypeError):
        return None

    nearest_hub = None
    nearest_distance = float('inf')

    for hub in rail_infrastructure:
        try:
            hub_lat = float(hub.get('latitude'))
            hub_lon = float(hub.get('longitude'))
            distance = calculate_distance(company_lat, company_lon, hub_lat, hub_lon)

            if distance and distance < nearest_distance:
                nearest_distance = distance
                nearest_hub = hub
        except (ValueError, TypeError):
            continue

    if nearest_hub:
        return {
            'hub_name': nearest_hub.get('location'),
            'hub_type': nearest_hub.get('type'),
            'distance_miles': round(nearest_distance, 1),
            'rail_connections': int(nearest_hub.get('rail_connections', 0)),
            'capacity_score': int(nearest_hub.get('capacity_score', 0)),
            'logistics_score': int(nearest_hub.get('logistics_score', 5)),
            'transload_hub': nearest_hub.get('transload_hub', 'No')
        }

    return None

def find_nearest_port(company):
    """
    Find the nearest major port and calculate maritime access score.
    Returns dict with port info and distance.
    """
    try:
        company_lat = float(company.get('latitude'))
        company_lon = float(company.get('longitude'))
    except (ValueError, TypeError):
        return None

    nearest_port = None
    nearest_distance = float('inf')

    for port_name, (port_lat, port_lon) in MAJOR_PORTS.items():
        distance = calculate_distance(company_lat, company_lon, port_lat, port_lon)

        if distance and distance < nearest_distance:
            nearest_distance = distance
            nearest_port = port_name

    if nearest_port and nearest_distance < 1000:  # Within 1000 miles
        return {
            'port_name': nearest_port,
            'distance_miles': round(nearest_distance, 1),
            'port_accessible': nearest_distance < 300  # Accessible if within 300 miles
        }

    return None

def find_nearest_major_city(company):
    """
    Find the nearest major metropolitan area.
    Returns dict with city info and distance.
    """
    try:
        company_lat = float(company.get('latitude'))
        company_lon = float(company.get('longitude'))
    except (ValueError, TypeError):
        return None

    nearest_city = None
    nearest_distance = float('inf')
    city_region = None

    for city_name, (city_lat, city_lon, region) in MAJOR_CITIES.items():
        distance = calculate_distance(company_lat, company_lon, city_lat, city_lon)

        if distance and distance < nearest_distance:
            nearest_distance = distance
            nearest_city = city_name
            city_region = region

    if nearest_city:
        return {
            'city_name': nearest_city,
            'region': city_region,
            'distance_miles': round(nearest_distance, 1),
            'consumer_market_access': nearest_distance < 200  # Strong access if within 200 miles
        }

    return None

def calculate_multimodal_score(company, rail_infrastructure):
    """
    Calculate a 1-100 multimodal logistics accessibility score.
    Considers rail, port, and interstate access.
    
    Scoring:
    - Rail hub proximity (40 points): Closer hubs = higher scores
    - Port accessibility (30 points): Coastal advantage
    - Interstate connectivity (20 points): Highway access
    - Consumer market proximity (10 points): Major city closeness
    """
    score = 0

    # Rail Hub Proximity (40 points max)
    rail_info = find_nearest_rail_hub(company, rail_infrastructure)
    if rail_info:
        distance = rail_info['distance_miles']
        rail_score = max(0, 40 - (distance / 10))  # Decreases with distance
        score += rail_score

    # Port Accessibility (30 points max)
    port_info = find_nearest_port(company)
    if port_info:
        if port_info['port_accessible']:
            score += 30  # Full points if within 300 miles
        else:
            distance = port_info['distance_miles']
            score += max(0, 30 - ((distance - 300) / 20))

    # Interstate Connectivity (20 points max)
    # This would ideally use GIS data; for now, use rail hub logistics score as proxy
    if rail_info:
        logistics_score = rail_info['logistics_score']
        score += (logistics_score / 10) * 20

    # Consumer Market Proximity (10 points max)
    city_info = find_nearest_major_city(company)
    if city_info:
        distance = city_info['distance_miles']
        if city_info['consumer_market_access']:
            score += 10
        else:
            score += max(0, 10 - (distance - 200) / 50)

    return min(100, round(score, 1))

def calculate_geographic_opportunity_score(company, rail_infrastructure):
    """
    Calculate regional economic opportunity score (1-100).
    Considers regional industrial base and growth potential.
    
    Regions scored by industrial potential:
    - South-Central (TX, OK, LA): +25 points (energy, petrochemicals)
    - Midwest (IL, IN, OH, MI): +20 points (auto, steel, machinery)
    - Pacific (CA, OR, WA): +20 points (tech, logistics, trade)
    - Southeast (GA, SC, NC, AL): +15 points (automotive, distribution)
    - Northeast (PA, NY, NJ, MA): +15 points (manufacturing, finance)
    - Mountain (CO, UT, AZ, NM): +10 points (mining, energy)
    - Southwest (TX, AZ, NM): +15 points (energy, logistics)
    """
    state = company.get('state', '').upper()

    # Regional scores
    region_scores = {
        # South-Central
        'TX': 25, 'OK': 25, 'LA': 25,
        # Midwest
        'IL': 20, 'IN': 20, 'OH': 20, 'MI': 20, 'WI': 18, 'MN': 18, 'IA': 15,
        # Pacific
        'CA': 20, 'OR': 20, 'WA': 20,
        # Southeast
        'GA': 15, 'SC': 15, 'NC': 15, 'AL': 15, 'TN': 12, 'VA': 12, 'FL': 10,
        # Northeast
        'PA': 15, 'NY': 15, 'NJ': 15, 'MA': 15, 'CT': 12,
        # Mountain
        'CO': 10, 'UT': 10, 'AZ': 10, 'NM': 10,
        # Great Plains
        'MO': 12, 'KS': 12, 'NE': 10,
    }

    base_score = region_scores.get(state, 5)

    # Bonus for proximity to major rail hub
    rail_info = find_nearest_rail_hub(company, rail_infrastructure)
    hub_bonus = 0
    if rail_info:
        distance = rail_info['distance_miles']
        if distance < 50:
            hub_bonus = 15
        elif distance < 100:
            hub_bonus = 10
        elif distance < 200:
            hub_bonus = 5

    return min(100, base_score + hub_bonus + 15)  # +15 base opportunity

def calculate_industrial_land_need(company):
    """
    Estimate industrial land requirements based on company profile.
    Returns estimated acreage needed for facility.
    
    Scoring by segment and commodity:
    - Steel mills: 100-500 acres
    - Scrap metal: 20-100 acres
    - Energy: 50-1000 acres
    - Automotive: 50-300 acres
    - Machinery: 30-200 acres
    - Warehousing: 50-500 acres
    """
    segment = company.get('segment', '').lower()
    commodity = company.get('commodity_type', '').lower()

    acreage_ranges = {
        'steel mills': (100, 500),
        'scrap metal': (20, 100),
        'energy': (50, 1000),
        'pipe and tube': (30, 150),
        'machinery': (30, 200),
        'automotive': (50, 300),
        'construction materials': (30, 200),
        'fabricators': (20, 100),
        'steel service centers': (15, 80),
        'warehousing': (50, 500),
    }

    min_acres, max_acres = acreage_ranges.get(segment, (20, 100))
    avg_acres = (min_acres + max_acres) / 2

    return {
        'estimated_minimum_acres': min_acres,
        'estimated_average_acres': int(avg_acres),
        'estimated_maximum_acres': max_acres,
        'segment': segment
    }

def get_geographic_intelligence(company, rail_infrastructure):
    """
    Generate comprehensive geographic intelligence profile for a company.
    
    Returns dict containing:
    - Rail hub proximity and access
    - Port accessibility for imports/exports
    - Major city/consumer market proximity
    - Multimodal logistics score
    - Regional opportunity score
    - Industrial land requirements
    - Geographic opportunity summary
    """
    rail_info = find_nearest_rail_hub(company, rail_infrastructure)
    port_info = find_nearest_port(company)
    city_info = find_nearest_major_city(company)
    land_needs = calculate_industrial_land_need(company)
    multimodal_score = calculate_multimodal_score(company, rail_infrastructure)
    geo_opportunity = calculate_geographic_opportunity_score(company, rail_infrastructure)

    return {
        'company': company.get('company'),
        'state': company.get('state'),
        'city': company.get('city'),
        'latitude': company.get('latitude'),
        'longitude': company.get('longitude'),
        'nearest_rail_hub': rail_info.get('hub_name') if rail_info else 'Unknown',
        'rail_distance_miles': rail_info.get('distance_miles') if rail_info else None,
        'rail_connections': rail_info.get('rail_connections') if rail_info else 0,
        'rail_logistics_score': rail_info.get('logistics_score') if rail_info else 0,
        'transload_hub_available': rail_info.get('transload_hub') if rail_info else 'No',
        'nearest_port': port_info.get('port_name') if port_info else 'Not accessible',
        'port_distance_miles': port_info.get('distance_miles') if port_info else None,
        'port_accessible': port_info.get('port_accessible') if port_info else False,
        'nearest_major_city': city_info.get('city_name') if city_info else 'Unknown',
        'city_distance_miles': city_info.get('distance_miles') if city_info else None,
        'region': city_info.get('region') if city_info else 'Unknown',
        'consumer_market_access': city_info.get('consumer_market_access') if city_info else False,
        'multimodal_logistics_score': multimodal_score,
        'geographic_opportunity_score': geo_opportunity,
        'industrial_land_minimum_acres': land_needs['estimated_minimum_acres'],
        'industrial_land_average_acres': land_needs['estimated_average_acres'],
        'industrial_land_maximum_acres': land_needs['estimated_maximum_acres'],
    }
