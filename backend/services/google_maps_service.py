"""
backend/services/google_maps_service.py
───────────────────────────────────────
Google Maps Platform Integration Service for Digital Twin Traffic AI.

Supported Google Cloud APIs (within $200/mo Free Tier):
  1. Directions API (Live Traffic & Travel Time Calibration)
  2. Street View Static API (Intersection 360° Visual Audits)
  3. Places API (Nearby Safety & Land-Use POIs: Schools, Hospitals, Transit)
  4. Geocoding API (Instant Place Search & Bounding Box Extraction)
"""

from __future__ import annotations

import logging
import os
import urllib.parse
from typing import Any

import requests

log = logging.getLogger("google_maps_service")


from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent


def get_api_key() -> str | None:
    """Retrieve Google Maps API Key from environment (dynamically reloading .env)."""
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env", override=True)
    except Exception:
        pass
    key = os.getenv("GOOGLE_MAPS_API_KEY") or os.getenv("VITE_GOOGLE_MAPS_API_KEY") or None
    if key and key.strip() and not key.startswith("your_"):
        return key.strip()
    return None


def is_available() -> bool:
    """Check if Google Maps API Key is configured."""
    return bool(get_api_key())


# ── 1. Street View Static API ──────────────────────────────────────────────────

def get_street_view_url(lat: float, lon: float, heading: int = 0, fov: int = 90, pitch: int = 0, size: str = "600x300") -> dict:
    """
    Generate Google Street View Static image URL and metadata for a given junction coordinate.
    """
    api_key = get_api_key()
    base_url = "https://maps.googleapis.com/maps/api/streetview"
    
    params = {
        "size": size,
        "location": f"{lat},{lon}",
        "fov": fov,
        "heading": heading,
        "pitch": pitch,
    }
    
    if api_key:
        params["key"] = api_key
        
    query_string = urllib.parse.urlencode(params)
    image_url = f"{base_url}?{query_string}"
    
    # Also generate Google Maps interactive Web URL
    interactive_url = f"https://www.google.com/maps/@?api=1&map_action=pano&viewpoint={lat},{lon}&heading={heading}&pitch={pitch}&fov={fov}"
    maps_pin_url = f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"

    return {
        "lat": lat,
        "lon": lon,
        "image_url": image_url,
        "interactive_street_view_url": interactive_url,
        "google_maps_pin_url": maps_pin_url,
        "is_configured": is_available(),
        "heading": heading,
    }


# ── 2. Directions API with Live Real-World Traffic ─────────────────────────────

def get_traffic_comparison(
    origin_lat: float,
    origin_lon: float,
    dest_lat: float,
    dest_lon: float,
    simulated_travel_time_s: float | None = None,
) -> dict:
    """
    Query Google Directions API with live traffic (departure_time=now) and compare
    real-world travel times against our SUMO simulated baseline travel times.
    """
    api_key = get_api_key()
    if not api_key:
        # Fallback simulation delta estimate if key not set
        base_tt = simulated_travel_time_s or 120.0
        return {
            "is_live_data": False,
            "status": "API_KEY_NOT_CONFIGURED",
            "message": "Google Maps API Key not set in .env (using calibrated estimation).",
            "origin": f"{origin_lat},{origin_lon}",
            "destination": f"{dest_lat},{dest_lon}",
            "google_traffic": {
                "distance_km": round((base_tt * 8.5) / 1000, 2),
                "duration_normal_min": round(base_tt / 60, 1),
                "duration_in_traffic_min": round((base_tt * 1.35) / 60, 1),
                "traffic_delay_min": round((base_tt * 0.35) / 60, 1),
                "congestion_level": "Moderate (Estimated)",
            },
            "simulated_vs_real_delta": {
                "simulated_duration_min": round((simulated_travel_time_s or base_tt) / 60, 1),
                "real_world_duration_min": round((base_tt * 1.35) / 60, 1),
                "variance_pct": 35.0,
            }
        }

    try:
        url = "https://maps.googleapis.com/maps/api/directions/json"
        params = {
            "origin": f"{origin_lat},{origin_lon}",
            "destination": f"{dest_lat},{dest_lon}",
            "departure_time": "now",
            "traffic_model": "best_guess",
            "key": api_key,
        }
        res = requests.get(url, params=params, timeout=10)
        data = res.json()

        if data.get("status") != "OK" or not data.get("routes"):
            return {
                "is_live_data": False,
                "status": data.get("status", "ZERO_RESULTS"),
                "error_message": data.get("error_message", "No route found"),
                "google_traffic": None,
            }

        route = data["routes"][0]
        leg = route["legs"][0]

        duration_s = leg.get("duration", {}).get("value", 0)
        duration_traffic_s = leg.get("duration_in_traffic", {}).get("value", duration_s)
        distance_m = leg.get("distance", {}).get("value", 0)

        traffic_delay_s = max(0, duration_traffic_s - duration_s)
        delay_ratio = duration_traffic_s / max(duration_s, 1)

        if delay_ratio > 1.5:
            congestion_level = "Severe Congestion (Red)"
        elif delay_ratio > 1.2:
            congestion_level = "Moderate Traffic (Orange)"
        else:
            congestion_level = "Smooth Flow (Green)"

        sim_tt = simulated_travel_time_s or duration_s
        variance_pct = round(((duration_traffic_s - sim_tt) / max(sim_tt, 1)) * 100, 1)

        return {
            "is_live_data": True,
            "status": "OK",
            "summary": route.get("summary", "Primary Corridor"),
            "origin_address": leg.get("start_address", ""),
            "destination_address": leg.get("end_address", ""),
            "google_traffic": {
                "distance_km": round(distance_m / 1000, 2),
                "duration_normal_min": round(duration_s / 60, 1),
                "duration_in_traffic_min": round(duration_traffic_s / 60, 1),
                "traffic_delay_min": round(traffic_delay_s / 60, 1),
                "congestion_level": congestion_level,
            },
            "simulated_vs_real_delta": {
                "simulated_duration_min": round(sim_tt / 60, 1),
                "real_world_duration_min": round(duration_traffic_s / 60, 1),
                "variance_pct": variance_pct,
            },
        }
    except Exception as e:
        log.error(f"Google Directions API call failed: {e}")
        return {
            "is_live_data": False,
            "status": "ERROR",
            "error_message": str(e),
            "google_traffic": None,
        }


# ── 3. Places API (Nearby Safety & Civic POIs) ─────────────────────────────────

def get_nearby_safety_pois(lat: float, lon: float, radius_m: int = 500) -> dict:
    """
    Fetch nearby schools, hospitals, transit hubs, and commercial centres
    around an intersection to generate context-aware zoning and safety rules.
    """
    api_key = get_api_key()
    if not api_key:
        return {
            "is_live_data": False,
            "status": "API_KEY_NOT_CONFIGURED",
            "radius_m": radius_m,
            "pois": [
                {"name": "Local School / College Zone", "type": "school", "distance_approx_m": 180, "safety_priority": "High (Pedestrian Zone)"},
                {"name": "City General Hospital / Clinic", "type": "hospital", "distance_approx_m": 320, "safety_priority": "Critical (Emergency Corridor)"},
                {"name": "Commercial Market / Bus Stop", "type": "transit_station", "distance_approx_m": 120, "safety_priority": "Medium (Footfall Zone)"},
            ],
            "zoning_advice": [
                "🏫 School within 200m: Mandate 25 km/h school speed limit & install pedestrian tabletop crossing.",
                "🏥 Hospital corridor: Enforce strict no-parking and emergency siren priority corridor.",
                "🚌 Bus stop nearby: Dedicated bus bay required to prevent 1-lane blockage during boarding.",
            ]
        }

    try:
        url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
        # Search for key institutional types
        params = {
            "location": f"{lat},{lon}",
            "radius": radius_m,
            "types": "school|hospital|transit_station|bus_station",
            "key": api_key,
        }
        res = requests.get(url, params=params, timeout=10)
        data = res.json()

        results = data.get("results", [])
        formatted_pois = []
        has_school = False
        has_hospital = False
        has_transit = False

        for p in results[:8]:
            types = p.get("types", [])
            p_type = "landmark"
            priority = "Normal"
            if "school" in types or "university" in types:
                p_type = "school"
                priority = "High (Pedestrian Zone)"
                has_school = True
            elif "hospital" in types or "doctor" in types or "health" in types:
                p_type = "hospital"
                priority = "Critical (Emergency Corridor)"
                has_hospital = True
            elif "transit_station" in types or "bus_station" in types:
                p_type = "transit"
                priority = "Medium (Footfall Zone)"
                has_transit = True

            formatted_pois.append({
                "name": p.get("name", "Unnamed POI"),
                "type": p_type,
                "vicinity": p.get("vicinity", ""),
                "rating": p.get("rating"),
                "safety_priority": priority,
            })

        advice = []
        if has_school:
            advice.append("🏫 School in vicinity: Mandate 25 km/h school speed zone and high-visibility zebra crossing.")
        if has_hospital:
            advice.append("🏥 Hospital in vicinity: Designate emergency vehicle priority corridor and acoustic quiet zone.")
        if has_transit:
            advice.append("🚌 Transit hub nearby: Install designated drop-off bay to prevent curb blocking.")
        if not advice:
            advice.append("🏙️ Standard mixed urban corridor: Maintain standard IRC signal phasing.")

        return {
            "is_live_data": True,
            "status": "OK",
            "total_found": len(results),
            "pois": formatted_pois,
            "zoning_advice": advice,
        }
    except Exception as e:
        log.error(f"Google Places API call failed: {e}")
        return {
            "is_live_data": False,
            "status": "ERROR",
            "error_message": str(e),
            "pois": [],
            "zoning_advice": [],
        }


# ── 4. Geocoding API (Strict Google Maps Platform) ────────────────────────────

def geocode_place(query: str) -> dict:
    """
    Convert a city / landmark name into precise latitude, longitude, and bounding box.
    Strictly uses the Google Maps Geocoding API with zero fallbacks.
    """
    api_key = get_api_key()

    if not api_key:
        return {
            "is_live_data": False,
            "query": query,
            "status": "API_KEY_NOT_CONFIGURED",
            "error_message": "Google Maps API Key is missing. Please add GOOGLE_MAPS_API_KEY to your .env file.",
        }

    try:
        url = "https://maps.googleapis.com/maps/api/geocode/json"
        params = {"address": query.strip(), "key": api_key}
        res = requests.get(url, params=params, timeout=12)
        data = res.json()

        status = data.get("status")

        if status == "OK" and data.get("results"):
            first = data["results"][0]
            geometry = first.get("geometry", {})
            location = geometry.get("location", {})
            viewport = geometry.get("viewport", {})

            return {
                "is_live_data": True,
                "provider": "Google Maps Geocoding API",
                "status": "OK",
                "formatted_address": first.get("formatted_address", query),
                "place_id": first.get("place_id", ""),
                "location_type": geometry.get("location_type", "APPROXIMATE"),
                "center": {
                    "lat": float(location.get("lat", 0.0)),
                    "lon": float(location.get("lng", 0.0)),
                },
                "bbox": {
                    "north": float(viewport.get("northeast", {}).get("lat", location.get("lat", 0.0) + 0.02)),
                    "south": float(viewport.get("southwest", {}).get("lat", location.get("lat", 0.0) - 0.02)),
                    "east": float(viewport.get("northeast", {}).get("lng", location.get("lng", 0.0) + 0.02)),
                    "west": float(viewport.get("southwest", {}).get("lng", location.get("lng", 0.0) - 0.02)),
                },
            }
        elif status == "ZERO_RESULTS":
            return {
                "is_live_data": False,
                "query": query,
                "status": "ZERO_RESULTS",
                "error_message": f"Google Maps found 0 locations for '{query}'. Please check the spelling or add state/country.",
            }
        elif status == "REQUEST_DENIED":
            err_msg = data.get("error_message", "Google Maps request denied.")
            return {
                "is_live_data": False,
                "query": query,
                "status": "REQUEST_DENIED",
                "error_message": f"Google Maps API error: {err_msg} (Make sure 'Geocoding API' is enabled in your Google Cloud project).",
            }
        elif status == "OVER_QUERY_LIMIT":
            return {
                "is_live_data": False,
                "query": query,
                "status": "OVER_QUERY_LIMIT",
                "error_message": "Google Maps API rate limit or quota exceeded.",
            }
        else:
            err_msg = data.get("error_message", f"Google API status: {status}")
            return {
                "is_live_data": False,
                "query": query,
                "status": status or "ERROR",
                "error_message": f"Google Maps error: {err_msg}",
            }

    except requests.exceptions.Timeout:
        return {
            "is_live_data": False,
            "query": query,
            "status": "TIMEOUT",
            "error_message": "Connection to Google Maps timed out. Please check your internet connection.",
        }
    except Exception as e:
        log.error(f"Google Geocoding API call failed: {e}")
        return {
            "is_live_data": False,
            "query": query,
            "status": "ERROR",
            "error_message": f"Google Geocoding request failed: {str(e)}",
        }

