"""
Configuration settings for Bengaluru SafeRoute application.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Base paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

# Load environment variables
load_dotenv(BASE_DIR / ".env")

# App configuration
APP_HOST = os.getenv("APP_HOST", "127.0.0.1")
APP_PORT = int(os.getenv("APP_PORT", "8050"))
DEBUG = os.getenv("DEBUG", "True").lower() in ("true", "1", "t")

# Database URL
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'bengaluru_saferoute.db'}")

# Geospatial parameters
GEOGRAPHIC_CRS = os.getenv("GEOGRAPHIC_CRS", "EPSG:4326")
PROJECTED_CRS = os.getenv("PROJECTED_CRS", "EPSG:32643")  # UTM Zone 43N for Bengaluru
CORRIDOR_BUFFER_METERS = float(os.getenv("CORRIDOR_BUFFER_METERS", "30.0"))

# Bengaluru reference geographic center
BENGALURU_CENTER = [12.9716, 77.5946]
DEFAULT_ZOOM = 12

# Mandatory safety disclaimer
SAFETY_DISCLAIMER = (
    "Safety information may be incomplete or outdated. "
    "Follow road signs, traffic rules, and on-road conditions."
)

# Popular Bengaluru locations with coordinates for user convenience
POPULAR_LOCATIONS = {
    "Majestic (KSR Railway Station)": {"lat": 12.9781, "lon": 77.5695, "desc": "Central Transit Hub"},
    "MG Road (Metro Station)": {"lat": 12.9754, "lon": 77.6066, "desc": "Central Business District"},
    "Indiranagar (100 Feet Road)": {"lat": 12.9784, "lon": 77.6408, "desc": "East Commercial Corridor"},
    "Koramangala (Sony World Junction)": {"lat": 12.9344, "lon": 77.6258, "desc": "South-East Tech Hub"},
    "Silk Board Junction": {"lat": 12.9177, "lon": 77.6238, "desc": "High Traffic ORR/Hosur Intersection"},
    "Hebbal Flyover (Outer Ring Rd)": {"lat": 13.0359, "lon": 77.5971, "desc": "North Arterial Gateway"},
    "Whitefield (ITPL)": {"lat": 12.9858, "lon": 77.7314, "desc": "Major Tech Corridor"},
    "Electronic City (Phase 1)": {"lat": 12.8452, "lon": 77.6602, "desc": "South Tech Enclave"},
    "Jayanagar (4th Block)": {"lat": 12.9298, "lon": 77.5833, "desc": "South Residential/Commercial"},
    "Malleshwaram (8th Cross)": {"lat": 13.0084, "lon": 77.5702, "desc": "North-West Cultural & Retail"},
    "Marathahalli (ORR Bridge)": {"lat": 12.9553, "lon": 77.7011, "desc": "East ORR Transit Junction"},
    "KR Puram (Hanging Bridge)": {"lat": 12.9982, "lon": 77.6625, "desc": "North-East Arterial Confluence"},
    "Yeshwanthpur (Railway Station)": {"lat": 13.0232, "lon": 77.5501, "desc": "North-West Transit Corridor"},
    "HSR Layout (BDA Complex)": {"lat": 12.9116, "lon": 77.6389, "desc": "South-East Sector"}
}

# Transport mode specifications
TRANSPORT_MODES = {
    "car": {
        "label": "Car / Four-Wheeler",
        "avg_speed_kmph": 32.0,
        "vulnerability_multiplier": 1.0,
        "network_type": "drive",
        "icon": "car"
    },
    "motorcycle": {
        "label": "Motorcycle / Two-Wheeler",
        "avg_speed_kmph": 28.0,
        "vulnerability_multiplier": 1.3,
        "network_type": "drive",
        "icon": "motorcycle"
    },
    "bicycle": {
        "label": "Bicycle",
        "avg_speed_kmph": 14.0,
        "vulnerability_multiplier": 1.6,
        "network_type": "bike",
        "icon": "bicycle"
    },
    "pedestrian": {
        "label": "Pedestrian",
        "avg_speed_kmph": 4.5,
        "vulnerability_multiplier": 2.0,
        "network_type": "walk",
        "icon": "walking"
    }
}

# Transparent Risk Scoring Weights
RISK_WEIGHTS = {
    "verified_blackspot": 25.0,
    "fatal_accident": 18.0,
    "grievous_accident": 10.0,
    "minor_accident": 4.0,
    "sharp_curve": 12.0,
    "moderate_curve": 6.0,
    "gentle_curve": 2.0,
    "unknown_speed_limit": 5.0,
    "rain_advisory": 10.0,
    "night_advisory": 8.0
}
