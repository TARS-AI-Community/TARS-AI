#!/usr/bin/env python3
"""
module_geolocation.py

Geolocation Module for TARS-AI Application.

This module provides geolocation services including latitude and longitude
coordinates, IP-based location detection, and location-aware features.
It supports custom callbacks to trigger actions upon detecting location changes
or specific geographic regions.

"""

import requests
import json

from modules.module_config import load_config

CONFIG = load_config()

IPIFY_API_URL = "https://api.ipify.org?format=json"
IPINFO_API_URL = "https://ipinfo.io"

GEOLOCATION = {
    "ip": None,
    "city": None,
    "region": None,
    "country": None,
    "lat": None,
    "lon": None,
    "postal": None,
    "timezone": None,
}


def get_my_ip_address():
    response = requests.get(
        IPIFY_API_URL,
    )
    return response.json().get("ip")


def get_location_info(ip):
    ipinfo_api_key = CONFIG["GEO_SERVICES"]["ipinfo_api_key"]
    if not ipinfo_api_key:
        print("IPInfo API key is not configured.")
        return None

    ipinfo_url = f"{IPINFO_API_URL}/{ip}"
    response = requests.get(ipinfo_url, auth=(ipinfo_api_key, ""))
    if response.status_code == 200:
        location_data = response.json()
        return location_data
    else:
        print(f"[GEO_SERVICES] Failed to get location info: {response.status_code}")
        return None


def update_geo_location():
    global GEOLOCATION
    ip = get_my_ip_address()
    location_info = get_location_info(ip)
    if location_info:
        location_info["ip"] = ip
        loc = location_info.pop("loc", None)
        if loc:
            lat, lon = loc.split(",")
            location_info["lat"] = lat
            location_info["lon"] = lon

        print("[GEO_SERVICES] Initializing service...")
        print("[GEO_SERVICES] ip:", location_info.get("ip"))
        print(
            "[GEO_SERVICES] lat:",
            location_info.get("lat"),
            "lon:",
            location_info.get("lon"),
        )
        GEOLOCATION.update(location_info)
    else:
        print("[GEO_SERVICES] Failed to find location.")
