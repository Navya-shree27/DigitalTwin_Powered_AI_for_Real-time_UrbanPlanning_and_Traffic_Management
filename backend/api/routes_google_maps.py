"""
backend/api/routes_google_maps.py
──────────────────────────────────
API Endpoints for Google Maps Platform Integration.

Endpoints:
  GET  /api/google-maps/status                       — Check API Key configuration & enabled features
  GET  /api/google-maps/street-view                  — Get Street View image & interactive 360 link
  POST /api/google-maps/traffic-compare              — Compare real-world Google traffic against simulation
  GET  /api/google-maps/nearby-pois                  — Fetch nearby schools, hospitals & transit POIs
  GET  /api/google-maps/geocode                      — Geocode place query to bounding box
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend.services import google_maps_service

log = logging.getLogger("routes_google_maps")
router = APIRouter(prefix="/api/google-maps", tags=["Google Maps Platform"])


class TrafficCompareRequest(BaseModel):
    origin_lat: float = Field(..., description="Origin latitude")
    origin_lon: float = Field(..., description="Origin longitude")
    dest_lat: float   = Field(..., description="Destination latitude")
    dest_lon: float   = Field(..., description="Destination longitude")
    simulated_travel_time_s: float | None = Field(default=None, description="Simulated travel time in seconds")


@router.get("/status")
def get_google_maps_status() -> dict:
    """Check if Google Maps API Key is active and which free features are ready."""
    has_key = google_maps_service.is_available()
    return {
        "is_configured": has_key,
        "monthly_credit": "$200.00 USD (Google Cloud Free Tier)",
        "features": {
            "directions_live_traffic": {"name": "Live Traffic & Travel Times", "free_tier_calls_per_month": "~40,000"},
            "street_view_static":      {"name": "Intersection Visual 360° Audits", "free_tier_calls_per_month": "~28,500"},
            "places_safety_pois":      {"name": "Nearby Safety & Land-Use POIs", "free_tier_calls_per_month": "~10,000"},
            "geocoding_smart_search":  {"name": "Global Place Search & Bounding Box", "free_tier_calls_per_month": "~40,000"},
        },
        "instructions": "Set GOOGLE_MAPS_API_KEY in your .env file to enable live Google Maps integration." if not has_key else "Google Maps Platform active.",
    }


@router.get("/street-view")
def get_street_view(
    lat: float = Query(..., description="Latitude of intersection"),
    lon: float = Query(..., description="Longitude of intersection"),
    heading: int = Query(0, ge=0, le=360, description="Camera heading in degrees"),
    fov: int = Query(90, ge=10, le=120, description="Field of view"),
    size: str = Query("600x300", description="Image resolution"),
) -> dict:
    """Get Google Street View Static image URL and interactive 360° view link."""
    return google_maps_service.get_street_view_url(lat=lat, lon=lon, heading=heading, fov=fov, size=size)


@router.post("/traffic-compare")
def compare_traffic(body: TrafficCompareRequest) -> dict:
    """Compare real-world Google Maps live traffic against SUMO simulated travel times."""
    return google_maps_service.get_traffic_comparison(
        origin_lat=body.origin_lat,
        origin_lon=body.origin_lon,
        dest_lat=body.dest_lat,
        dest_lon=body.dest_lon,
        simulated_travel_time_s=body.simulated_travel_time_s,
    )


@router.get("/nearby-pois")
def get_nearby_pois(
    lat: float = Query(..., description="Latitude of intersection"),
    lon: float = Query(..., description="Longitude of intersection"),
    radius_m: int = Query(500, ge=50, le=2000, description="Search radius in meters"),
) -> dict:
    """Fetch nearby institutional & safety POIs (schools, hospitals, transit)."""
    return google_maps_service.get_nearby_safety_pois(lat=lat, lon=lon, radius_m=radius_m)


@router.get("/geocode")
def geocode_place(
    query: str = Query(..., description="City or landmark name to search"),
) -> dict:
    """Geocode place name to latitude/longitude center and bounding box."""
    return google_maps_service.geocode_place(query=query)
