"""
OmniMapping Geography Module
Handles geographic intelligence, mapping, and location-based analysis.

Integrated with geographic_scoring module for advanced proximity and logistics analysis.
"""

import math
import folium
import os
from geopy.distance import geodesic
from .scoring import safe_int
from .geographic_scoring import (
    get_geographic_intelligence,
    calculate_multimodal_score,
    calculate_geographic_opportunity_score,
    find_nearest_rail_hub,
    find_nearest_port,
    find_nearest_major_city
)

def haversine_distance(lat1, lon1, lat2, lon2):
    """Calculate the great circle distance between two points in miles"""
    try:
        coord1 = (float(lat1), float(lon1))
        coord2 = (float(lat2), float(lon2))
        return geodesic(coord1, coord2).miles
    except (ValueError, TypeError):
        return None

def calculate_rail_proximity_score(company, rail_infrastructure):
    """Calculate proximity to rail infrastructure"""
    if not (company.get('latitude') and company.get('longitude')):
        return None

    company_lat = float(company['latitude'])
    company_lon = float(company['longitude'])

    min_distance = float('inf')
    nearest_rail = None

    for rail in rail_infrastructure:
        if rail.get('latitude') and rail.get('longitude'):
            distance = haversine_distance(company_lat, company_lon,
                                        float(rail['latitude']), float(rail['longitude']))
            if distance and distance < min_distance:
                min_distance = distance
                nearest_rail = rail

    return min_distance, nearest_rail

def enhance_company_geography(companies, rail_infrastructure):
    """Add geographic intelligence to company data"""
    # City coordinates (simplified - in production would use geocoding API)
    city_coordinates = {
        'Birmingham': (33.5186, -86.8104),
        'Pittsburgh': (40.4406, -79.9959),
        'Cleveland': (41.4993, -81.6944),
        'Fort Wayne': (41.0793, -85.1394),
        'Middletown': (39.5151, -84.3983),
        'East Chicago': (41.6539, -87.4548),
        'Irving': (32.8140, -96.9489),
        'Portland': (45.5152, -122.6784),
        'San Leandro': (37.7249, -122.1561),
        'Chicago': (41.8781, -87.6298),
        'Greenville': (34.8526, -82.3940),
        'Southfield': (42.4734, -83.2219),
        'Oklahoma City': (35.4676, -97.5164),
        'Houston': (29.7604, -95.3698),
        'San Ramon': (37.7638, -121.9546),
        'Peoria': (40.6936, -89.5890),
        'Moline': (41.5067, -90.5151),
        'Omaha': (41.2565, -95.9345),
        'Fort Worth': (32.7555, -97.3308),
        'Georgetown': (38.2098, -84.5588),
        'Dearborn': (42.3223, -83.1763),
        'Detroit': (42.3314, -83.0458),
        'Seattle': (47.6062, -122.3321),
        'Bethesda': (38.9847, -77.0947),
        'Falls Church': (38.8823, -77.1711),
        'Midland': (43.6156, -84.2472),
        'Baytown': (29.7355, -94.9774),
        'Irving': (32.8140, -96.9489),
        'Kingsport': (36.5484, -82.5618),
        'The Woodlands': (30.1658, -95.4613),
        'Clayton': (38.6426, -90.3237),
        'Philadelphia': (39.9526, -75.1652),
        'Cincinnati': (39.1031, -84.5120),
        'Medina': (41.1384, -81.8637),
        'Livonia': (42.3684, -83.3527),
        'Toledo': (41.6528, -83.5379),
        'Glenview': (42.0698, -87.7878),
        'St. Louis': (38.6270, -90.1994),
        'St. Paul': (44.9537, -93.0900),
        'Columbus': (39.9612, -82.9988),
        'Wichita': (37.6872, -97.3301),
        'Louisville': (38.2527, -85.7585),
        'Wichita': (37.6872, -97.3301),
        'Birmingham': (33.5186, -86.8104),
        'Dallas': (32.7767, -96.7970),
        'Atlanta': (33.7490, -84.3880),
        'Denver': (39.7392, -104.9903)
    }

    # Major ports
    major_ports = {
        'Houston': 'Port Houston',
        'Los Angeles': 'Port of Los Angeles',
        'Long Beach': 'Port of Long Beach',
        'New York': 'Port of New York/New Jersey',
        'Savannah': 'Port of Savannah',
        'Seattle': 'Port of Seattle',
        'Tacoma': 'Port of Tacoma',
        'Oakland': 'Port of Oakland',
        'Portland': 'Port of Portland',
        'Stockton': 'Port of Stockton'
    }

    # Class 1 railroads
    class1_railroads = {
        'UP': 'Union Pacific',
        'BNSF': 'BNSF Railway',
        'NS': 'Norfolk Southern',
        'CSX': 'CSX Transportation',
        'KCS': 'Kansas City Southern',
        'CN': 'Canadian National',
        'CP': 'Canadian Pacific'
    }

    enhanced_companies = []

    for company in companies:
        enhanced_company = company.copy()

        # Add coordinates if city is known
        city = company.get('city', '')
        if city in city_coordinates:
            enhanced_company['latitude'] = city_coordinates[city][0]
            enhanced_company['longitude'] = city_coordinates[city][1]

        # Add nearest major city (simplified)
        state = company.get('state', '')
        if state in ['TX', 'CA', 'IL', 'PA', 'OH', 'IN']:
            enhanced_company['nearest_major_city'] = {
                'TX': 'Houston', 'CA': 'Los Angeles', 'IL': 'Chicago',
                'PA': 'Pittsburgh', 'OH': 'Cleveland', 'IN': 'Indianapolis'
            }.get(state)

        # Add nearest port
        if city in major_ports:
            enhanced_company['nearest_port'] = major_ports[city]
        elif state == 'TX':
            enhanced_company['nearest_port'] = 'Port Houston'
        elif state == 'CA':
            enhanced_company['nearest_port'] = 'Port of Los Angeles'

        # Add nearest Class 1 railroad (simplified)
        if state in ['TX', 'CA', 'IL', 'PA', 'OH', 'IN']:
            enhanced_company['nearest_class1_railroad'] = {
                'TX': 'Union Pacific', 'CA': 'Union Pacific', 'IL': 'BNSF Railway',
                'PA': 'Norfolk Southern', 'OH': 'Norfolk Southern', 'IN': 'CSX Transportation'
            }.get(state)

        # Calculate estimated rail distance (simplified)
        if enhanced_company.get('nearest_class1_railroad'):
            # Mock distance calculation - in production would use actual rail network
            enhanced_company['estimated_rail_distance'] = 15.0  # miles
        else:
            enhanced_company['estimated_rail_distance'] = 50.0

        # Add industrial land need estimate
        segment = company.get('segment', '').lower()
        if segment in ['steel mills', 'chemicals', 'energy']:
            enhanced_company['industrial_land_need'] = '500+ acres'
        elif segment in ['warehousing/distribution', 'construction materials']:
            enhanced_company['industrial_land_need'] = '100-200 acres'
        else:
            enhanced_company['industrial_land_need'] = '50-100 acres'

        # Add transload potential
        if segment in ['steel mills', 'scrap metal', 'construction materials', 'energy']:
            enhanced_company['transload_potential'] = 'High'
        elif segment in ['pipe and tube', 'chemicals']:
            enhanced_company['transload_potential'] = 'Medium'
        else:
            enhanced_company['transload_potential'] = 'Low'

        # Add port to consumer score (simplified)
        port_score = 0
        if enhanced_company.get('nearest_port'):
            port_score += 30
        if enhanced_company.get('transload_potential') == 'High':
            port_score += 20
        if state in ['TX', 'CA', 'FL', 'GA']:
            port_score += 25
        enhanced_company['port_to_consumer_score'] = port_score

        enhanced_companies.append(enhanced_company)

    return enhanced_companies

def generate_company_map(companies, output_dir="maps"):
    """Generate an interactive HTML map of all companies"""
    os.makedirs(output_dir, exist_ok=True)

    # Create base map centered on US
    m = folium.Map(location=[39.8283, -98.5795], zoom_start=4)

    # Add company markers
    for company in companies:
        if company.get('latitude') and company.get('longitude'):
            lat = float(company['latitude'])
            lon = float(company['longitude'])

            # Color code by priority score
            score = safe_int(company.get('priority_score', 0))
            if score >= 90:
                color = 'red'
            elif score >= 70:
                color = 'orange'
            elif score >= 50:
                color = 'blue'
            else:
                color = 'gray'

            # Create popup content
            popup_content = f"""
            <b>{company.get('company', 'Unknown')}</b><br>
            Location: {company.get('city', 'Unknown')}, {company.get('state', 'Unknown')}<br>
            Segment: {company.get('segment', 'Unknown')}<br>
            Priority Score: {score}/100<br>
            Rail Fit: {company.get('rail_fit_score', 'N/A')}/5
            """

            folium.CircleMarker(
                location=[lat, lon],
                radius=6,
                popup=popup_content,
                color=color,
                fill=True,
                fill_color=color
            ).add_to(m)

    # Save map
    map_file = os.path.join(output_dir, "companies_map.html")
    m.save(map_file)
    print(f"Company map saved to {map_file}")
    return map_file

def generate_sites_map(sites, output_dir="maps"):
    """Generate an interactive HTML map of industrial sites"""
    os.makedirs(output_dir, exist_ok=True)

    # Create base map
    m = folium.Map(location=[39.8283, -98.5795], zoom_start=4)

    # City coordinates for sites (simplified)
    site_coordinates = {
        'Denver': (39.7392, -104.9903),
        'Savannah': (32.0809, -81.0912),
        'Brownsville': (25.9018, -97.4975),
        'Tulsa': (36.1540, -95.9928),
        'Chicago': (41.8781, -87.6298),
        'Northern Colorado': (40.2677, -105.7089),
        'Port of Catoosa': (36.1834, -95.7508),
        'River Ridge': (29.9608, -90.2156),
        'Stockton': (37.9577, -121.2908)
    }

    # Add site markers
    for site in sites:
        city = site.get('city', '')
        if city in site_coordinates:
            lat, lon = site_coordinates[city]

            # Color code by rail service
            color = 'green' if site.get('rail_served', '').lower() in ['yes', 'true', '1'] else 'gray'

            # Create popup content
            popup_content = f"""
            <b>{site.get('site_name', 'Unknown Site')}</b><br>
            Location: {city}, {site.get('state', 'Unknown')}<br>
            Rail Served: {site.get('rail_served', 'No')}<br>
            Acres: {site.get('acres', 'Unknown')}<br>
            Transload: {site.get('transload_available', 'No')}<br>
            Port Access: {site.get('port_access', 'No')}<br>
            Target Industries: {site.get('target_industries', 'General')}
            """

            folium.Marker(
                location=[lat, lon],
                popup=popup_content,
                icon=folium.Icon(color=color, icon='industry', prefix='fa')
            ).add_to(m)

    # Save map
    map_file = os.path.join(output_dir, "industrial_sites_map.html")
    m.save(map_file)
    print(f"Industrial sites map saved to {map_file}")
    return map_file

def generate_top_opportunities_map(companies, limit=20, output_dir="maps"):
    """Generate a map of top opportunity companies"""
    os.makedirs(output_dir, exist_ok=True)

    # Get top companies
    from .search import get_top_opportunities
    top_companies = get_top_opportunities(companies, limit)

    # Create base map
    m = folium.Map(location=[39.8283, -98.5795], zoom_start=4)

    # Add markers for top opportunities
    for i, company in enumerate(top_companies, 1):
        if company.get('latitude') and company.get('longitude'):
            lat = float(company['latitude'])
            lon = float(company['longitude'])

            # Create popup content
            popup_content = f"""
            <b>#{i} Opportunity</b><br>
            <b>{company.get('company', 'Unknown')}</b><br>
            Location: {company.get('city', 'Unknown')}, {company.get('state', 'Unknown')}<br>
            Segment: {company.get('segment', 'Unknown')}<br>
            Priority Score: {company.get('priority_score', '0')}/100<br>
            Rail Fit: {company.get('rail_fit_score', 'N/A')}/5<br>
            Industrial Real Estate: {company.get('industrial_real_estate_score', 'N/A')}/5
            """

            folium.Marker(
                location=[lat, lon],
                popup=popup_content,
                icon=folium.Icon(color='red', icon='star', prefix='fa')
            ).add_to(m)

    # Save map
    map_file = os.path.join(output_dir, f"top_{limit}_opportunities_map.html")
    m.save(map_file)
    print(f"Top opportunities map saved to {map_file}")
    return map_file

def analyze_geographic_clusters(companies):
    """Analyze geographic clustering of companies"""
    from collections import defaultdict

    # Group by state
    state_clusters = defaultdict(list)
    for company in companies:
        state = company.get('state', 'Unknown')
        if company.get('latitude') and company.get('longitude'):
            state_clusters[state].append(company)

    # Calculate cluster statistics
    cluster_analysis = {}
    for state, company_list in state_clusters.items():
        if len(company_list) > 1:
            # Calculate centroid
            avg_lat = sum(float(c['latitude']) for c in company_list) / len(company_list)
            avg_lon = sum(float(c['longitude']) for c in company_list) / len(company_list)

            # Calculate spread
            distances = []
            for c1 in company_list:
                for c2 in company_list:
                    if c1 != c2:
                        dist = haversine_distance(float(c1['latitude']), float(c1['longitude']),
                                                float(c2['latitude']), float(c2['longitude']))
                        if dist:
                            distances.append(dist)

            avg_distance = sum(distances) / len(distances) if distances else 0

            cluster_analysis[state] = {
                'company_count': len(company_list),
                'centroid_lat': avg_lat,
                'centroid_lon': avg_lon,
                'avg_distance_between_companies': round(avg_distance, 1),
                'companies': company_list
            }

    return cluster_analysis

def get_multimodal_logistics_profile(company, rail_infrastructure):
    """
    Generate a comprehensive multimodal logistics profile for a company.
    Includes rail, port, and interstate accessibility scores.
    """
    rail_info = find_nearest_rail_hub(company, rail_infrastructure)
    port_info = find_nearest_port(company)
    city_info = find_nearest_major_city(company)
    multimodal_score = calculate_multimodal_score(company, rail_infrastructure)
    
    return {
        'company': company.get('company'),
        'city': company.get('city'),
        'state': company.get('state'),
        'rail_hub': rail_info.get('hub_name') if rail_info else 'Unknown',
        'rail_distance_miles': rail_info.get('distance_miles') if rail_info else None,
        'rail_connections': rail_info.get('rail_connections') if rail_info else 0,
        'rail_capacity_score': rail_info.get('capacity_score') if rail_info else 0,
        'transload_available': rail_info.get('transload_hub') if rail_info else 'No',
        'nearest_port': port_info.get('port_name') if port_info else 'Not accessible',
        'port_distance_miles': port_info.get('distance_miles') if port_info else None,
        'port_accessible': port_info.get('port_accessible') if port_info else False,
        'nearest_major_city': city_info.get('city_name') if city_info else 'Unknown',
        'city_region': city_info.get('region') if city_info else 'Unknown',
        'multimodal_logistics_score': multimodal_score
    }

def get_regional_opportunity_analysis(company, rail_infrastructure):
    """
    Analyze regional economic development opportunity for a company.
    Considers regional industrial base, growth potential, and logistics connectivity.
    """
    geo_opportunity_score = calculate_geographic_opportunity_score(company, rail_infrastructure)
    rail_info = find_nearest_rail_hub(company, rail_infrastructure)
    
    state = company.get('state', 'Unknown')
    region = 'Unknown'
    
    # Determine region
    if state in ['TX', 'OK', 'LA']:
        region = 'South-Central (Energy Hub)'
    elif state in ['IL', 'IN', 'OH', 'MI', 'WI', 'MN', 'IA']:
        region = 'Midwest (Manufacturing Hub)'
    elif state in ['CA', 'OR', 'WA']:
        region = 'Pacific (Trade & Tech Hub)'
    elif state in ['GA', 'SC', 'NC', 'AL', 'TN', 'VA', 'FL']:
        region = 'Southeast (Automotive & Distribution)'
    elif state in ['PA', 'NY', 'NJ', 'MA', 'CT']:
        region = 'Northeast (Industrial Base)'
    elif state in ['CO', 'UT', 'AZ', 'NM']:
        region = 'Mountain (Mining & Energy)'
    
    return {
        'company': company.get('company'),
        'state': state,
        'region': region,
        'regional_opportunity_score': geo_opportunity_score,
        'nearest_major_hub': rail_info.get('hub_name') if rail_info else 'Unknown',
        'hub_distance_miles': rail_info.get('distance_miles') if rail_info else None,
        'hub_type': rail_info.get('hub_type') if rail_info else 'Unknown',
        'logistics_rating': rail_info.get('logistics_score') if rail_info else 0
    }

def generate_geographic_opportunity_map(companies, rail_infrastructure, output_dir="maps"):
    """
    Generate an advanced geographic opportunity map with multimodal connectivity scoring.
    Shows companies color-coded by geographic opportunity score.
    """
    os.makedirs(output_dir, exist_ok=True)
    
    # Create base map
    m = folium.Map(location=[39.8283, -98.5795], zoom_start=4)
    
    # Add company markers with geographic scoring
    for company in companies:
        if company.get('latitude') and company.get('longitude'):
            lat = float(company['latitude'])
            lon = float(company['longitude'])
            
            # Calculate geographic opportunity score
            geo_score = calculate_geographic_opportunity_score(company, rail_infrastructure)
            multimodal_score = calculate_multimodal_score(company, rail_infrastructure)
            
            # Color code by geographic opportunity
            if geo_score >= 80:
                color = 'darkred'
            elif geo_score >= 60:
                color = 'red'
            elif geo_score >= 50:
                color = 'orange'
            elif geo_score >= 40:
                color = 'blue'
            else:
                color = 'gray'
            
            # Get logistics info
            rail_info = find_nearest_rail_hub(company, rail_infrastructure)
            port_info = find_nearest_port(company)
            
            # Create detailed popup
            popup_content = f"""
            <b>{company.get('company', 'Unknown')}</b><br>
            Location: {company.get('city', 'Unknown')}, {company.get('state', 'Unknown')}<br>
            <hr>
            <b>Geographic Opportunity Score: {int(geo_score)}/100</b><br>
            <b>Multimodal Logistics Score: {int(multimodal_score)}/100</b><br>
            <hr>
            <b>Rail Infrastructure:</b><br>
            • Nearest Hub: {rail_info.get('hub_name') if rail_info else 'Unknown'}<br>
            • Distance: {rail_info.get('distance_miles') if rail_info else 'Unknown'} miles<br>
            • Connections: {rail_info.get('rail_connections') if rail_info else 0}<br>
            • Transload: {rail_info.get('transload_hub') if rail_info else 'No'}<br>
            <hr>
            <b>Maritime Access:</b><br>
            • Nearest Port: {port_info.get('port_name') if port_info else 'Not accessible'}<br>
            • Distance: {port_info.get('distance_miles') if port_info else 'Unknown'} miles<br>
            • Accessible: {port_info.get('port_accessible') if port_info else 'No'}<br>
            """
            
            folium.CircleMarker(
                location=[lat, lon],
                radius=8,
                popup=folium.Popup(popup_content, max_width=300),
                color=color,
                fill=True,
                fill_color=color,
                weight=2,
                opacity=0.9,
                fill_opacity=0.7
            ).add_to(m)
    
    # Save map
    map_file = os.path.join(output_dir, "geographic_opportunity_map.html")
    m.save(map_file)
    print(f"Geographic opportunity map saved to {map_file}")
    return map_file

def export_geographic_profiles(companies, rail_infrastructure, filename="geographic_profiles.csv"):
    """
    Export comprehensive geographic profiles for all companies to CSV.
    """
    import csv
    
    # Get full geographic intelligence for each company
    profiles = []
    for company in companies:
        geo_intel = get_geographic_intelligence(company, rail_infrastructure)
        profiles.append(geo_intel)
    
    if not profiles:
        print("No geographic profiles to export.")
        return
    
    # Export to CSV
    fieldnames = list(profiles[0].keys())
    with open(filename, 'w', newline='') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(profiles)
    
    print(f"Exported geographic profiles for {len(profiles)} companies to {filename}")

    return filename
