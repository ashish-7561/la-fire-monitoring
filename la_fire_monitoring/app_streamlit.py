# app_streamlit.py  — LA Fire + AQ Monitor (LIVE)
import os
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

# LA County bounding box (covers all of LA County)
# Ref bounds: west≈-118.95, east≈-117.65, south≈33.70, north≈34.82
LA_BBOX = (-118.951721, 33.704538, -117.646374, 34.823302)  # (west, south, east, north)

# Read API keys from env or Streamlit secrets
FIRMS_KEY = os.getenv("FIRMS_MAP_KEY") or st.secrets.get("FIRMS_MAP_KEY", None)
OPENAQ_KEY = os.getenv("OPENAQ_API_KEY") or st.secrets.get("OPENAQ_API_KEY", None)

# Base endpoints
FIRMS_BASE = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"
OPENAQ_BASE = "https://api.openaq.org/v3"

# =========================
# Sidebar controls
# =========================
with st.sidebar:
    st.header("Controls")
    hours_back = st.slider("Fire window (hours)", min_value=3, max_value=72, value=24, step=3)
    max_fire_points = st.slider("Max fire markers to plot", 100, 5000, 1200, step=100)
    st.caption("Note: We cap markers for performance; raw CSV can contain more.")

    st.markdown("---")
    pm_sensor_limit = st.slider("Max PM2.5 sensors", min_value=5, max_value=50, value=20, step=5)
    st.caption("We’ll compute NowCast per sensor then summarize across LA.")

    st.markdown("---")
    st.write("API keys")
    st.write(f"FIRMS key set: {'✅' if FIRMS_KEY else '❌'}")
    st.write(f"OpenAQ key set: {'✅' if OPENAQ_KEY else '❌'}")

# =========================
# Helpers: AQI (NowCast)
# =========================
# EPA NowCast for PM2.5 (uses last 12 hourly concentrations, µg/m3)
# w = max(0.5, c_min/c_max). NowCast = sum(w^(i-1)*c_i)/sum(w^(i-1)), i=1..12, c1 is most recent
def nowcast_pm25(last_12_hours):
    vals = [v for v in last_12_hours if v is not None and not math.isnan(v)]
    if len(vals) < 2:
        return None
    cmax = max(vals)
    cmin = min(vals)
    if cmax <= 0:
        return 0.0
    w = max(0.5, cmin / cmax)
    weights = np.array([w ** i for i in range(len(vals))])  # oldest to newest
    # we built oldest->newest; NowCast uses c1 as most recent, so reverse vals for proper weighting
    vals_rev = np.array(list(reversed(vals)))
    weights = np.array([w ** i for i in range(len(vals_rev))])
    return float(np.sum(weights * vals_rev) / np.sum(weights))

# Map PM2.5 concentration (µg/m3) to AQI using current EPA breakpoints (2024 updates)
# Breakpoints table (PM2.5, 24-hr / NowCast), µg/m3:
# 0.0-9.0 → 0-50; 9.1-35.4 → 51-100; 35.5-55.4 → 101-150; 55.5-125.4 → 151-200
# 125.5-225.4 → 201-300; 225.5-325.4 → 301-500
def pm25_to_aqi(c):
    if c is None:
        return None
    # define breakpoints
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
            return round(( (c - Clow) / (Chigh - Clow) ) * (Ihigh - Ilow) + Ilow)
    # above 325.4 → cap at 500
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
    if not FIRMS_KEY:
        raise RuntimeError("Missing FIRMS_MAP_KEY")
    # Sensors: VIIRS SNPP, NOAA-20, NOAA-21 — fetch & concat
    sensors = ["VIIRS_SNPP_NRT", "VIIRS_NOAA20_NRT", "VIIRS_NOAA21_NRT"]
    frames = []
    for s in sensors:
        url = f"{FIRMS_BASE}/{FIRMS_KEY}/{s}/{west},{south},{east},{north}/{hours}"
        r = requests.get(url, timeout=60)
        r.raise_for_status()
        # Some responses can be empty for a sensor in small windows
        if r.text.strip():
            df = pd.read_csv(pd.compat.StringIO(r.text))
            df["sensor"] = s
            frames.append(df)
        time.sleep(0.2)  # be polite
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    # Standard column names in FIRMS CSV (latitude, longitude, acq_date, acq_time, confidence, frp, etc.)
    # Keep only the most relevant & recent rows
    out["acq_datetime"] = pd.to_datetime(out["acq_date"] + " " + out["acq_time"].astype(str).str.zfill(4), format="%Y-%m-%d %H%M", errors="coerce")
    out = out.sort_values("acq_datetime", ascending=False)
    return out.head(max_rows)

@st.cache_data(ttl=600)
def fetch_openaq_pm25_hours_bbox(west, south, east, north, sensor_limit=20):
    if not OPENAQ_KEY:
        raise RuntimeError("Missing OPENAQ_API_KEY")

    headers = {"X-API-Key": OPENAQ_KEY}

    # 1) Find locations in bbox that measure PM2.5 (parameter id 2 == pm2.5 per OpenAQ)
    params = {
        "bbox": f"{west},{south},{east},{north}",
        "parameters_id": 2,
        "limit": 100,
        "page": 1,
        "sort": "desc",
        "order_by": "lastUpdated"
    }
    r = requests.get(f"{OPENAQ_BASE}/locations", params=params, headers=headers, timeout=60)
    r.raise_for_status()
    locs = r.json().get("results", [])
    if not locs:
        return pd.DataFrame(), []

    # pick top N locations, then fetch their PM2.5 sensors and last 12 hours
    sensor_rows = []
    now_utc = dt.datetime.utcnow()
    from_utc = now_utc - dt.timedelta(hours=13)  # request >12 hours to ensure completeness

    for loc in locs[:sensor_limit]:
        loc_id = loc["id"]
        # sensors under a location
        r2 = requests.get(f"{OPENAQ_BASE}/locations/{loc_id}/sensors", params={"parameters_id": 2, "limit": 10}, headers=headers, timeout=60)
        if r2.status_code != 200:
            continue
        sensors = r2.json().get("results", [])
        for s in sensors:
            sid = s["id"]
            # hourly values for the sensor
            r3 = requests.get(
                f"{OPENAQ_BASE}/sensors/{sid}/hours",
                params={
                    "date_from": from_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "date_to":   now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "limit": 1000
                },
                headers=headers, timeout=60
            )
            if r3.status_code != 200:
                continue
            rows = r3.json().get("results", [])
            # build time series (most recent last)
            ts = []
            for row in rows:
                # Depending on provider, PM2.5 can be "ug/m³" or similar; assume µg/m3 numeric in "value"
                ts.append((row["period"]["datetimeTo"]["utc"], row["value"]))
            ts = sorted(ts, key=lambda x: x[0])  # oldest -> newest
            values = [v for _, v in ts][-12:]  # last 12 hours
            nc = nowcast_pm25(values)
            aqi = pm25_to_aqi(nc if nc is not None else (values[-1] if values else None))
            latest = values[-1] if values else None
            sensor_rows.append({
                "location_id": loc_id,
                "location_name": loc["name"],
                "sensor_id": sid,
                "pm25_latest_ugm3": latest,
                "pm25_nowcast_ugm3": nc,
                "aqi_nowcast": aqi,
                "category": aqi_category(aqi),
                "lat": loc["coordinates"]["latitude"] if loc.get("coordinates") else None,
                "lon": loc["coordinates"]["longitude"] if loc.get("coordinates") else None,
            })
        time.sleep(0.15)

    df = pd.DataFrame(sensor_rows)
    return df, locs

# =========================
# UI: Fetch + show data
# =========================
# Guardrails: keys present?
if not FIRMS_KEY:
    st.error("FIRMS_MAP_KEY is missing. Set it via environment (%env FIRMS_MAP_KEY=...) or st.secrets and reload.")
if not OPENAQ_KEY:
    st.error("OPENAQ_API_KEY is missing. Set it via environment (%env OPENAQ_API_KEY=...) or st.secrets and reload.")

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
            # Build the map centered on LA
            m = folium.Map(location=[34.05, -118.25], zoom_start=9, tiles="cartodbpositron")
            mc = MarkerCluster().add_to(m)
            for _, row in fires.iterrows():
                lat = row.get("latitude")
                lon = row.get("longitude")
                conf = str(row.get("confidence", ""))
                frp = row.get("frp", "")
                acq_dt = row.get("acq_datetime")
                sensor = row.get("sensor")
                # basic styling by confidence
                color = "red" if str(conf).lower() in ["high", "n"] else "orange" if str(conf).lower() in ["nominal","med","medium"] else "yellow"
                popup = folium.Popup(html=f"""
                    <b>Sensor:</b> {sensor}<br>
                    <b>Acquired:</b> {acq_dt}<br>
                    <b>Confidence:</b> {conf}<br>
                    <b>FRP:</b> {frp}
                """, max_width=260)
                folium.CircleMarker(
                    location=[lat, lon], radius=5, color=color, fill=True, fill_opacity=0.7, popup=popup
                ).add_to(mc)
            st_folium(m, height=520, width=None)
            st.caption("Source: NASA FIRMS VIIRS ‘Area’ API within an LA County bounding box.")
    except Exception as e:
        st.exception(e)

# ---------- AQI PANEL ----------
with col_right:
    st.subheader("Air Quality — PM₂.₅ NowCast AQI (OpenAQ)")
    try:
        sensors_df, locs_raw = fetch_openaq_pm25_hours_bbox(*LA_BBOX, sensor_limit=pm_sensor_limit)
        if sensors_df.empty:
            st.warning("No PM₂.₅ sensors found in OpenAQ for this area/time.")
        else:
            # summarize citywide
            worst_row = sensors_df.loc[sensors_df["aqi_nowcast"].idxmax()]
            city_avg_aqi = int(round(sensors_df["aqi_nowcast"].mean()))
            c1, c2 = st.columns(2)
            with c1:
                st.metric("Citywide average NowCast AQI", f"{city_avg_aqi}", delta=None)
            with c2:
                st.metric("Worst site NowCast AQI", f"{int(worst_row['aqi_nowcast'])}", help=f"{worst_row['location_name']}")

            st.write("Top sensors (latest):")
            show_cols = ["location_name", "aqi_nowcast", "category", "pm25_nowcast_ugm3", "pm25_latest_ugm3"]
            st.dataframe(
                sensors_df.sort_values("aqi_nowcast", ascending=False)[show_cols].reset_index(drop=True),
                use_container_width=True
            )

            # small plot: distribution by category
            cat_counts = sensors_df["category"].value_counts().reset_index()
            cat_counts.columns = ["AQI Category", "Count"]
            st.bar_chart(cat_counts.set_index("AQI Category"))

            # Add sensor markers on a small map below
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
            st.caption("Source: OpenAQ v3 hourly data. NowCast computed per US EPA method; AQI categories per EPA 2024 update.")
    except Exception as e:
        st.exception(e)

st.markdown("---")
st.info(
    "Notes: Fire detections from NASA FIRMS (VIIRS) within the LA County bounding box; "
    "PM₂.₅ NowCast computed from the last 12 hourly observations per sensor and mapped to AQI using EPA breakpoints."
)