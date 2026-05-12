"""
OmniMapping Configuration
Centralized configuration management for the platform.
"""

import os
from pathlib import Path

# Project paths
PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / "data"
EXPORTS_DIR = PROJECT_ROOT / "exports"
MAPS_DIR = PROJECT_ROOT / "maps"
TEMPLATES_DIR = PROJECT_ROOT / "templates"

# Data files
COMPANIES_FILE = DATA_DIR / "companies.csv"
SEGMENTS_FILE = DATA_DIR / "segments.csv"
SITES_FILE = DATA_DIR / "industrial_sites.csv"
RAIL_FILE = DATA_DIR / "rail_infrastructure.csv"
REVIEW_STORE_FILE = DATA_DIR / "review_status.json"

# Geographic data (simplified city coordinates)
CITY_COORDINATES = {
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
    'Dallas': (32.7767, -96.7970),
    'Denver': (39.7392, -104.9903),
    'Albany': (31.5785, -84.1557),
    'Atlanta': (33.7490, -84.3880),
    'Brownsville': (25.9017, -97.4975),
    'Catoosa': (36.1889, -95.7458),
    'Gadsden': (34.0143, -86.0066),
    'Grant': (40.8411, -101.7252),
    'Jeffersonville': (38.2776, -85.7372),
    'Kettle Falls': (48.6107, -118.0558),
    'Maricopa': (33.0581, -112.0476),
    'Martinsburg': (39.4562, -77.9639),
    'Massena': (44.9281, -74.8919),
    'Mead': (40.2333, -104.9986),
    'Moorefield': (39.0623, -78.9695),
    'Muskogee': (35.7479, -95.3697),
    'Ottawa': (41.3456, -88.8426),
    'Rincon': (32.2960, -81.2354),
    'San Saba': (31.1957, -98.7181),
    'Santa Maria': (34.9530, -120.4357),
    'Stockton': (37.9577, -121.2908),
    'Tulsa': (36.1540, -95.9928),
    'Washington': (38.9072, -77.0369),
    'Windsor': (40.4775, -104.9014),
}

# Scoring weights and constants
SCORING_WEIGHTS = {
    'rail_fit': 25,
    'logistics_intensity': 20,
    'land_intensity': 15,
    'multimodal_potential': 15,
    'site_match_quality': 10,
    'industry_fit': 10,
    'strategic_fit': 5,
}

# UI settings
DEFAULT_TOP_LIMIT = 20
MAX_EXPORT_LIMIT = 500

# Flask settings
FLASK_DEBUG = True
FLASK_HOST = '0.0.0.0'
FLASK_PORT = 5000
