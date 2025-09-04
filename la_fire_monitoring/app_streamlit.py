# app_streamlit.py — LA Fire + AQ Monitor (LIVE)

import os
import io
import math
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

# FIRMS Endpoints
FIRMS_CONUS = "https://firms.modaps.eosdis.nasa.gov/data/active_fire/viirs/csv/VNP14IMGTDL_NRT_CONUS.csv"
FIRMS_API = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"

# Your NASA FIRMS Token (put it in Streamlit secrets or env var in production)
FIRMS_TOKEN = os.getenv("FIRMS_TOKEN") or "eyJ0eXAiOiJKV1QiLCJvcmlnaW4iOiJFYXJ0aGRhdGEgTG9naW4iLCJzaWciOiJlZGxqd3RwdWJrZXlfb3BzIiwiYWxnIjoiUlMyNTYifQ.eyJ0eXBlIjoiVXNlciIsInVpZCI6ImFkaGQ1Njg5IiwiZXhwIjoxNzYyMjE0Mzk5LCJpYXQiOjE3NTY5NzUyODEsImlzcyI6Imh0dHBzOi8vdXJzLmVhcnRoZGF0YS5uYXNhLmdvdiIsImlkZW50aXR5X3Byb3ZpZGVyIjoiZWRsX29wcyIsImFjciI6ImVkbCIsImFzc3VyYW5jZV9sZXZlbCI6M30.Th8Ka13kkUjIY_YWUrzfhU4LtLaYk7ZlVpAtghMrw-dCZLbcrabfoG8hiYoTZQ1bNFavq_oVTZboOYQEbCFSIshr6bNup0yMEdb6hvGJfEEMtU3RAtYVDkCCRRJ8zzKJcAO112Ezva8DfuEF-Eemy9QWSn8xH2jmpB2x7gQqUrfJQIbjc8jrkNVWlyFp-UqDIyxJHtVC6YjUsmMvf54JJqQm7-6dyKiitaExECOgxUYW7PfHGryxtsaM6sZuLHfDXaT0VqRrPYI2-6utY2aEa9E3uyCQ0umgekfhIwME8C8sh_daCn3e48YXzuxGtDbkKX6GuhzIpk0AoSmPcBBB9g"

OPENAQ_BASE_V2 = "https://api.openaq.org/v2"

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
    if FIRMS_TOKEN:
        st.write("FIRMS: ✅ Using NASA API with token")
    else:
        st.write("FIRMS: ⚠️ Using slower CONUS CSV fallback")
    st.write("OpenAQ: ✅ Free v2 API")

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
            return round(((c - Clow) / (Chigh - Clow)) * (Ihigh - Ilow) + Ilow)
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
    """Fetch VIIRS fire detections. Prefer NASA API with token; fallback to CONUS CSV."""
    try:
        if FIRMS_TOKEN:
            bbox = f"{west},{south},{east},{north}"
            url = f"{FIRMS_API}/VIIRS_NOAA20_NRT/{hours}h/{bbox}"
            headers = {"Authorization": f"Bearer {FIRMS_TOKEN}"}
            r = requests.get(url, headers=headers, timeout=60)
            r.raise_for_status()
            df = pd.read_csv(io.StringIO(r.text))
            df["sensor"] = "VIIRS_API"
        else:
            raise ValueError("No FIRMS token, using fallback.")
    except Exception:
        r = requests.get(FIRMS_CONUS, timeout=60)
        r.raise_for_status()
        df = pd.read_csv(io.StringIO(r.text))
        df = df[(df["longitude"].between(west, east)) & (df["latitude"].between(south, north))]
        df["sensor"] = "VIIRS_CONUS"

    # datetime + filter
    df["acq_datetime"] = pd.to_datetime(
        df["acq_date"].astype(str) + " " + df["acq_time"].astype(str).str.zfill(4),
        format="%Y-%m-%d %H%M", errors="coerce"
    )
    cutoff = dt.datetime.utcnow() - dt.timedelta(hours=hours)
    df = df[df["acq_datetime"] >= cutoff]
    df = df.sort_values("acq_datetime", ascending=False)
    return df.head(max_rows)

@st.cache_data(ttl=600)
def fetch_openaq_pm25_hours_bbox(west, south, east, north, sensor_limit=20):
    """Fetch PM2.5 hourly values from OpenAQ v2 (free, no key)."""
    params = {
        "parameter": "pm25",
        "limit": sensor_limit,
        "sort": "desc",
        "order_by": "lastUpdated",
        "bbox": f"{west},{south},{east},{north}",
    }
    r = requests.get(f"{OPENAQ_BASE_V2}/latest", params=params, timeout=60)
    r.raise_for_status()
    results = r.json().get("results", [])
    sensor_rows = []

    for loc in results:
        if "coordinates" not in loc:
            continue
        lat, lon = loc["coordinates"]["latitude"], loc["coordinates"]["longitude"]
        location_name = loc.get("location", "Unknown")
        values = [m["value"] for m in loc.get("measurements", []) if m.get("parameter") == "pm25"]
        if not values:
            continue
        latest = values[0]
        nc = nowcast_pm25(values[:12])
        aqi = pm25_to_aqi(nc if nc is not None else latest)
        sensor_rows.append({
            "location_name": location_name,
            "pm25_latest_ugm3": latest,
            "pm25_nowcast_ugm3": nc,
            "aqi_nowcast": aqi,
            "category": aqi_category(aqi),
            "lat": lat,
            "lon": lon,
        })

    df = pd.DataFrame(sensor_rows)
    return df, results

# =========================
# UI: Fire + AQ
# =========================
col_map, col_right = st.columns([1.1, 1])

# ---------- FIRE MAP ----------
with col_map:
    st.subheader(f"Active Fire Detections (NASA VIIRS, last {hours_back}h)")
    try:
        west, south, east, north = LA_BBOX
        fires = fetch_firms_viirs_bbox(west, south, east, north, hours=hours_back, max_rows=max_fire_points)
        if fires.empty:
            st.warning("No recent VIIRS fire detections found in the selected window.")
        else:
            m = folium.Map(location=[34.05, -118.25], zoom_start=9, tiles="cartodbpositron")
            mc = MarkerCluster().add_to(m)
            for _, row in fires.iterrows():
                lat, lon = row["latitude"], row["longitude"]
                conf = str(row.get("confidence", ""))
                acq_dt, frp = row.get("acq_datetime"), row.get("frp", "")
                color = "red" if str(conf).lower() in ["high", "n"] else "orange" if str(conf).lower() in ["nominal","med","medium"] else "yellow"
                popup = folium.Popup(html=f"""
                    <b>Sensor:</b> {row['sensor']}<br>
                    <b>Acquired:</b> {acq_dt}<br>
                    <b>Confidence:</b> {conf}<br>
                    <b>FRP:</b> {frp}
                """, max_width=260)
                folium.CircleMarker(
                    location=[lat, lon], radius=5, color=color, fill=True, fill_opacity=0.7, popup=popup
                ).add_to(mc)
            st_folium(m, height=520, width=None)
    except Exception as e:
        st.exception(e)

# ---------- AQI PANEL ----------
with col_right:
    st.subheader("Air Quality — PM₂.₅ NowCast AQI (OpenAQ v2)")
    try:
        sensors_df, _ = fetch_openaq_pm25_hours_bbox(*LA_BBOX, sensor_limit=pm_sensor_limit)
        if sensors_df.empty:
            st.warning("No PM₂.₅ sensors found in OpenAQ for this area/time.")
        else:
            worst_row = sensors_df.loc[sensors_df["aqi_nowcast"].idxmax()]
            city_avg_aqi = int(round(sensors_df["aqi_nowcast"].mean()))
            c1, c2 = st.columns(2)
            with c1:
                st.metric("Citywide average NowCast AQI", f"{city_avg_aqi}")
            with c2:
                st.metric("Worst site NowCast AQI", f"{int(worst_row['aqi_nowcast'])}", help=f"{worst_row['location_name']}")

            show_cols = ["location_name", "aqi_nowcast", "category", "pm25_nowcast_ugm3", "pm25_latest_ugm3"]
            st.dataframe(
                sensors_df.sort_values("aqi_nowcast", ascending=False)[show_cols].reset_index(drop=True),
                use_container_width=True
            )

            cat_counts = sensors_df["category"].value_counts().reset_index()
            cat_counts.columns = ["AQI Category", "Count"]
            st.bar_chart(cat_counts.set_index("AQI Category"))

            st.markdown("*Sensor locations*")
            m2 = folium.Map(location=[34.05, -118.25], zoom_start=9, tiles="cartodbpositron")
            for _, r in sensors_df.dropna(subset=["lat","lon"]).iterrows():
                aqi = r["aqi_nowcast"]
                folium.CircleMarker(
                    location=[r["lat"], r["lon"]],
                    radius=6,
                    color=aqi_color(aqi),
                    fill=True,
                    fill_opacity=0.9,
                    popup=folium.Popup(f"{r['location_name']} — AQI {int(aqi)} ({aqi_category(aqi)})", max_width=280)
                ).add_to(m2)
            st_folium(m2, height=300, width=None)
    except Exception as e:
        st.exception(e)

st.markdown("---")
st.info(
    "Notes: Fire detections from NASA FIRMS VIIRS (API or public CONUS dataset) filtered to LA County; "
    "PM₂.₅ NowCast computed from OpenAQ v2 latest data; AQI categories per EPA 2024 updates."
)
