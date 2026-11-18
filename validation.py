"""
Validation and integrity constraints for Bengaluru SafeRoute.
"""

from typing import Tuple, Dict, Any, Optional
from src.config import TRANSPORT_MODES


BENGALURU_BBOX = {
    "min_lat": 12.5,
    "max_lat": 13.5,
    "min_lon": 77.2,
    "max_lon": 78.0
}


def is_in_bengaluru_bounds(lat: float, lon: float) -> bool:
    """Validate that coordinates fall within the broader Bengaluru metropolitan region."""
    return (
        BENGALURU_BBOX["min_lat"] <= lat <= BENGALURU_BBOX["max_lat"] and
        BENGALURU_BBOX["min_lon"] <= lon <= BENGALURU_BBOX["max_lon"]
    )


def validate_route_inputs(
    start_lat: float,
    start_lon: float,
    dest_lat: float,
    dest_lon: float,
    mode: str,
    buffer_meters: float
) -> Tuple[bool, Optional[str]]:
    """Validate user input parameters for route safety calculation."""
    if not is_in_bengaluru_bounds(start_lat, start_lon):
        return False, f"Start location ({start_lat:.4f}, {start_lon:.4f}) is outside the Bengaluru coverage area."

    if not is_in_bengaluru_bounds(dest_lat, dest_lon):
        return False, f"Destination ({dest_lat:.4f}, {dest_lon:.4f}) is outside the Bengaluru coverage area."

    if abs(start_lat - dest_lat) < 0.0001 and abs(start_lon - dest_lon) < 0.0001:
        return False, "Start location and destination must be distinct points."

    if mode.lower() not in TRANSPORT_MODES:
        valid_modes = ", ".join(TRANSPORT_MODES.keys())
        return False, f"Invalid transport mode '{mode}'. Choose from: {valid_modes}"

    if buffer_meters < 5.0 or buffer_meters > 500.0:
        return False, "Route safety corridor buffer must be between 5 and 500 metres."

    return True, None


def validate_blackspot_eligibility(source_type: str, status: str) -> Tuple[bool, Optional[str]]:
    """
    Enforces policy: Data from media reports or news may only be stored as reference,
    and must never be recorded as a verified blackspot.
    """
    if source_type in ("media_report", "news_archive") and status in ("verified_official", "verified_admin"):
        return False, "Media and news-based records cannot be designated as verified blackspots without official corroboration."
    return True, None
