# app_streamlit.py — LA Fire + AQ Monitor (LIVE)

import os
import io
import math
import time
import requests
import datetime as dt
import pandas as pd
import numpy as np
import streamlit as st
import folium
from streamlit_folium import st_folium
from folium.plugins import MarkerCluster

# =========================
# Page / constants
# =========================
st.set_page_config(layout="wide", page_title="LA Fire + AQ Monitor (Live)")
st.title("Los Angeles Fire Incidents & Air Quality (Live)")

LA_BBOX = (-118.951721, 33.704538, -117.646374, 34.823302)  # (west, south, east, north)

# Read API keys from env or Streamlit secrets
FIRMS_KEY = os.getenv("FIRMS_MAP_KEY") or st.secrets.get("FIRMS_MAP_KEY", None)
OPENAQ_KEY = os.getenv("OPENAQ_API_KEY") or st.secrets.get("OPENAQ_API_KEY", None)

# Base endpoints
FIRMS_BASE = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"
FIRMS_CONUS = "https://firms.modaps.eosdis.nasa.gov/data/active_fire/viirs/csv/VNP14IMGTDL_NRT_CONUS.csv"
OPENAQ_BASE = "https://api.openaq.org/v3"

# =========================
# Sidebar controls
# =========================
with st.sidebar:
    st.header("Controls")
    hours_back = st.slider("Fire window (hours)", min_value=3, max_value=72, value=24, step=3)
    max_fire_points = st.slider("Max fire markers to plot", 100, 5000, 1200, step=100)

    st.markdown("---")
    pm_sensor_limit = st.slider("Max PM2.5 sensors", min_value=5, max_value=50, value=20, step=5)

    st.markdown("---")
    st.write("API keys")
    st.write(f"FIRMS key set: {'✅' if FIRMS_KEY else '❌ (using fallback)'}")
    st.write(f"OpenAQ key set: {'✅' if OPENAQ_KEY else '❌'}")

# =========================
# Helpers: AQI (NowCast)
# =========================
def nowcast_pm25(last_12_hours):
    vals = [v for v in last_12_hours if v is not None and not math.isnan(v)]
    if len(vals) < 2:
        return None
    cmax, cmin = max(vals), min(vals)
    if cmax <= 0:
        return 0.0
    w = max(0.5, cmin / cmax)
    vals_rev = list(reversed(vals))
    weights = np.array([w ** i for i in range(len(vals_rev))])
    return float(np.sum(weights * vals_rev) / np.sum(weights))

def pm25_to_aqi(c):
    if c is None:
        return None
    bps = [
        (0.0, 9.0, 0, 50),
        (9.1, 35.4, 51, 100),
        (35.5, 55.4, 101, 150),
        (55.5, 125.4, 151, 200),
        (125.5, 225.4, 201, 300),
        (225.5, 325.4, 301, 500),
    ]
    for Clow, Chigh, Ilow, Ihigh in bps:
        if Clow <= c <= Chigh:
            return round(((c - Clow) / (Chigh - Ilow)) * (Ihigh - Ilow) + Ilow)
    return 500

def aqi_category(aqi):
    if aqi is None: return "Unknown"
    if aqi <= 50: return "Good"
    if aqi <= 100: return "Moderate"
    if aqi <= 150: return "Unhealthy for Sensitive Groups"
    if aqi <= 200: return "Unhealthy"
    if aqi <= 300: return "Very Unhealthy"
    return "Hazardous"

def aqi_color(aqi):
    if aqi is None: return "#999999"
    if aqi <= 50: return "#00e400"
    if aqi <= 100: return "#ffff00"
    if aqi <= 150: return "#ff7e00"
    if aqi <= 200: return "#ff0000"
    if aqi <= 300: return "#8f3f97"
    return "#7e0023"

# =========================
# Data fetchers (cached)
# =========================
@st.cache_data(ttl=600)
def fetch_firms_viirs_bbox(west, south, east, north, hours=24, max_rows=10000):
    # --- CASE 1: use NASA API (requires key) ---
    if FIRMS_KEY:
        sensors = ["VIIRS_SNPP_NRT", "VIIRS_NOAA20_NRT", "VIIRS_NOAA21_NRT"]
        frames = []
        for s in sensors:
            url = f"{FIRMS_BASE}/{FIRMS_KEY}/{s}/{west},{south},{east},{north}/{hours}"
            r = requests.get(url, timeout=60)
            if r.status_code != 200 or not r.text.strip():
                continue
            df = pd.read_csv(io.StringIO(r.text))
            df["sensor"] = s
            frames.append(df)
            time.sleep(0.2)
        if not frames:
            return pd.DataFrame()
        out = pd.concat(frames, ignore_index=True)

    # --- CASE 2: fallback to public CONUS CSV ---
    else:
        r = requests.get(FIRMS_CONUS, timeout=60)
        r.raise_for_status()
        df = pd.read_csv(io.StringIO(r.text))
        # filter by bbox
        df = df[(df["longitude"].between(west, east)) & (df["latitude"].between(south, north))]
        df["sensor"] = "VIIRS_CONUS"
        out = df.copy()

    # add datetime, sort, limit
    if "acq_date" in out.columns and "acq_time" in out.columns:
        out["acq_datetime"] = pd.to_datetime(
            out["acq_date"].astype(str) + " " + out["acq_time"].astype(str).str.zfill(4),
            format="%Y-%m-%d %H%M", errors="coerce"
        )
        out = out.sort_values("acq_datetime", ascending=False)
    return out.head(max_rows)

# (fetch_openaq_pm25_hours_bbox remains the same — requires OPENAQ_KEY)

