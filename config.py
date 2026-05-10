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
