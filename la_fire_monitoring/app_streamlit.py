import os
import requests
import pandas as pd
import streamlit as st
from datetime import datetime

# -------------------------
# Config
# -------------------------
OPENAQ_BASE_V3 = "https://api.openaq.org/v3"
OPENAQ_API_KEY = "2bb377049f03246178ba3eac129990f113325cb1c86935ab0aa7c506522d23ce"  # your key

# NASA FIRMS (Collection 7 datasets)
NASA_FIRMS_URL_VIIRS = "https://firms.modaps.eosdis.nasa.gov/data/active_fire/viirs/snpp-npp-c2/csv/Global_VNP14IMGTDL_NRT.csv"
NASA_FIRMS_URL_MODIS = "https://firms.modaps.eosdis.nasa.gov/data/active_fire/modis/c6_1/csv/MODIS_C6_1_Global_24h.csv"

# ✅ FIX: Correct header format
HEADERS = {"X-API-Key": OPENAQ_API_KEY}

# -------------------------
# Utility functions
# -------------------------
def nowcast_pm25(values):
    """Simple NowCast average."""
    if not values:
        return None
    return round(sum(values) / len(values), 1)

def pm25_to_aqi(pm):
    """Convert PM2.5 (µg/m³) to AQI (US EPA breakpoints)."""
    if pm is None:
        return None
    breakpoints = [
        (0.0, 12.0, 0, 50),
        (12.1, 35.4, 51, 100),
        (35.5, 55.4, 101, 150),
        (55.5, 150.4, 151, 200),
        (150.5, 250.4, 201, 300),
        (250.5, 350.4, 301, 400),
        (350.5, 500.4, 401, 500),
    ]
    for bp_low, bp_high, aqi_low, aqi_high in breakpoints:
        if bp_low <= pm <= bp_high:
            return round((aqi_high - aqi_low) / (bp_high - bp_low) * (pm - bp_low) + aqi_low)
    return 500

def aqi_category(aqi):
    """Return AQI category string."""
    if aqi is None:
        return "Unknown"
    if aqi <= 50: return "Good"
    if aqi <= 100: return "Moderate"
    if aqi <= 150: return "Unhealthy for Sensitive"
    if aqi <= 200: return "Unhealthy"
    if aqi <= 300: return "Very Unhealthy"
    return "Hazardous"

# -------------------------
# Data Fetching
# -------------------------
@st.cache_data(ttl=3600)
def fetch_nasa_firms_global():
    """Fetch NASA FIRMS global active fires (last 24h)."""
    try:
        df = pd.read_csv(NASA_FIRMS_URL_VIIRS)
    except:
        df = pd.read_csv(NASA_FIRMS_URL_MODIS)
    return df

@st.cache_data(ttl=600)
def fetch_openaq_pm25_hours_bbox(west, south, east, north, sensor_limit=20):
    """Fetch PM2.5 data from OpenAQ API v3 within bounding box (fallback to Los Angeles)."""
    params = {
        "bbox": f"{west},{south},{east},{north}",
        "parameter": "pm25",
        "limit": sensor_limit,
        "sort": "desc",
        "order_by": "datetimeLastUpdated"  # ✅ FIX: correct field
    }
    url = f"{OPENAQ_BASE_V3}/locations"
    r = requests.get(url, headers=HEADERS, params=params, timeout=60)
    r.raise_for_status()
    results = r.json().get("results", [])

    # Fallback if empty
    if not results:
        r = requests.get(
            url,
            headers=HEADERS,
            params={"city": "Los Angeles", "parameter": "pm25", "limit": 20},
            timeout=60
        )
        r.raise_for_status()
        results = r.json().get("results", [])

    sensor_rows = []
    for loc in results:
        coords = loc.get("coordinates") or {}
        lat, lon = coords.get("latitude"), coords.get("longitude")
        if lat is None or lon is None:
            continue
        pm = next((m.get("lastValue") for m in loc.get("parameters", []) if m.get("parameter") == "pm25"), None)
        if pm is None:
            continue
        nc = nowcast_pm25([pm])
        aqi = pm25_to_aqi(nc if nc is not None else pm)
        sensor_rows.append({
            "location_name": loc.get("name", "Unknown"),
            "pm25_latest_ugm3": pm,
            "pm25_nowcast_ugm3": nc,
            "aqi_nowcast": aqi,
            "category": aqi_category(aqi),
            "lat": lat,
            "lon": lon,
        })

    df = pd.DataFrame(sensor_rows)
    return df, results

# -------------------------
# Streamlit App
# -------------------------
st.set_page_config(page_title="Fires & Air Quality Dashboard", layout="wide")
st.title("🌍 Wildfire & Air Quality Monitoring Dashboard")

# Sidebar
st.sidebar.header("Configuration")
region = st.sidebar.selectbox("Region", ["Global", "Custom Bounding Box"])

if region == "Custom Bounding Box":
    west = st.sidebar.number_input("West (lon)", -180.0, 180.0, -125.0)
    south = st.sidebar.number_input("South (lat)", -90.0, 90.0, 32.0)
    east = st.sidebar.number_input("East (lon)", -180.0, 180.0, -114.0)
    north = st.sidebar.number_input("North (lat)", -90.0, 90.0, 42.0)
else:
    west, south, east, north = -180, -90, 180, 90

# Data fetching
st.sidebar.markdown("### Data Sources")
try:
    df_aq, _ = fetch_openaq_pm25_hours_bbox(west, south, east, north, sensor_limit=50)
    st.sidebar.success("✅ OpenAQ v3 connected")
except Exception as e:
    df_aq = pd.DataFrame()
    st.sidebar.error(f"OpenAQ error: {e}")

try:
    df_fires = fetch_nasa_firms_global()
    st.sidebar.success("✅ NASA FIRMS connected")
except Exception as e:
    df_fires = pd.DataFrame()
    st.sidebar.error(f"NASA FIRMS error: {e}")

# -------------------------
# Layout
# -------------------------
col1, col2 = st.columns(2)

with col1:
    st.subheader("🔥 Active Fires (NASA FIRMS)")
    if not df_fires.empty:
        st.map(df_fires.rename(columns={"latitude": "lat", "longitude": "lon"}))
        st.write(df_fires.head())
    else:
        st.write("No fire data available.")

with col2:
    st.subheader("🌫️ Air Quality — PM₂.₅ NowCast AQI (OpenAQ v3)")
    if not df_aq.empty:
        st.dataframe(df_aq)
        st.map(df_aq)
    else:
        st.write("No air quality data available.")

