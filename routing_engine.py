
from pathlib import Path
import math

import networkx as nx
import numpy as np
import pandas as pd
from geopy.geocoders import Nominatim, Photon


# ============================================================================
# BENGALURU COVERAGE BOUNDARY
# ============================================================================

LAT_MIN, LAT_MAX = 12.70, 13.25
LON_MIN, LON_MAX = 77.30, 77.85


# ============================================================================
# GEOCODING — NOMINATIM PRIMARY + PHOTON BACKUP
# ============================================================================

def geocode_location(query):
    """
    Resolve a Bengaluru location.

    Online providers are tried first. If both public geocoding services are
    temporarily unavailable, known Bengaluru neighbourhoods/landmarks can
    still be resolved locally. Local fallback coordinates are approximate;
    the routing engine subsequently snaps them to the nearest road node.
    """
    query = str(query).strip()

    if not query:
        raise ValueError("Enter a source or destination.")

    # Approximate fallback coordinates for common Bengaluru areas.
    # These are neighbourhood/landmark anchors, not live address matches.
    fallback_locations = {
        "majestic": ("Kempegowda Bus Station (Majestic)", 12.9767, 77.5713),
        "kempegowda bus station": ("Kempegowda Bus Station (Majestic)", 12.9767, 77.5713),
        "kempegowda bus stand": ("Kempegowda Bus Station (Majestic)", 12.9767, 77.5713),
        "indiranagar": ("Indiranagar Metro Station area", 12.9784, 77.6408),
        "indiranagar metro station": ("Indiranagar Metro Station area", 12.9784, 77.6408),
        "koramangala": ("Koramangala", 12.9352, 77.6245),
        "koramangala 1st block": ("Koramangala 1st Block", 12.9279, 77.6271),
        "koramangala 5th block": ("Koramangala 5th Block", 12.9345, 77.6149),
        "whitefield": ("Whitefield", 12.9698, 77.7500),
        "electronic city": ("Electronic City", 12.8452, 77.6602),
        "electronic city phase 1": ("Electronic City Phase 1", 12.8399, 77.6770),
        "electronic city phase 2": ("Electronic City Phase 2", 12.8480, 77.6750),
        "mg road": ("Mahatma Gandhi Road", 12.9756, 77.6068),
        "brigade road": ("Brigade Road", 12.9719, 77.6011),
        "cubbon park": ("Cubbon Park", 12.9763, 77.5929),
        "vijayanagar": ("Vijayanagar", 12.9700, 77.5380),
        "jayanagar": ("Jayanagar", 12.9250, 77.5838),
        "hebbal": ("Hebbal", 13.0358, 77.5970),
        "marathahalli": ("Marathahalli", 12.9560, 77.7010),
        "sarjapur": ("Sarjapur", 12.9100, 77.6870),
        "hsr layout": ("HSR Layout", 12.9116, 77.6389),
        "btm layout": ("BTM Layout", 12.9166, 77.6101),
        "banashankari": ("Banashankari", 12.9255, 77.5468),
        "rajajinagar": ("Rajajinagar", 13.0108, 77.5550),
        "yeshwanthpur": ("Yeshwanthpur", 13.0285, 77.5400),
        "malleshwaram": ("Malleshwaram", 13.0031, 77.5643),
        "bellandur": ("Bellandur", 12.9304, 77.6784),
        "kr puram": ("KR Puram", 13.0075, 77.6950),
        "k r puram": ("KR Puram", 13.0075, 77.6950),
    }

    normalized = " ".join(
        query.lower().replace(",", " ").replace("-", " ").split()
    )
    local_match = fallback_locations.get(normalized)

    # Resolve known example areas immediately; this avoids depending on
    # third-party uptime for the locations shown in the project demo.
    if local_match is not None:
        label, lat, lon = local_match
        return {
            "query": query,
            "address": f"{label}, Bengaluru, Karnataka, India (approximate local fallback)",
            "lat": lat,
            "lon": lon,
            "geocoding_provider": "Local Bengaluru fallback"
        }

    # Online geocoding for other neighbourhoods and full street addresses.
    search_query = f"{query}, Bengaluru, Karnataka, India"
    errors = []

    # Build providers separately. This simpler form also makes the
    # parentheses unambiguous in GitHub/Streamlit deployments.
    providers = []

    try:
