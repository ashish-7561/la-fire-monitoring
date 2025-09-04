import requests
import pandas as pd
import streamlit as st

# -------------------------
# Config
# -------------------------
WAQI_TOKEN = "3cd76abad0501e79bb285944bee4c559a17d69ba"

NASA_FIRMS_URL_VIIRS = "https://firms.modaps.eosdis.nasa.gov/data/active_fire/viirs/snpp-npp-c2/csv/Global_VNP14IMGTDL_NRT.csv"
NASA_FIRMS_URL_MODIS = "https://firms.modaps.eosdis.nasa.gov/data/active_fire/modis/c6_1/csv/MODIS_C6_1_Global_24h.csv"

# -------------------------
# Utility functions
# -------------------------
def pm25_to_aqi(pm):
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
    if aqi is None: return "Unknown"
    if aqi <= 50: return "Good"
    if aqi <= 100: return "Moderate"
    if aqi <= 150: return "Unhealthy (Sensitive)"
    if aqi <= 200: return "Unhealthy"
    if aqi <= 300: return "Very Unhealthy"
    return "Hazardous"

# -------------------------
# Data Fetching
# -------------------------
@st.cache_data(ttl=3600)
def fetch_nasa_firms_global():
    try:
        df = pd.read_csv(NASA_FIRMS_URL_VIIRS)
    except:
        df = pd.read_csv(NASA_FIRMS_URL_MODIS)
    return df

@st.cache_data(ttl=600)
def fetch_waqi_city(city="Delhi"):
    url = f"https://api.waqi.info/feed/{city}/?token={WAQI_TOKEN}"
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    data = r.json()
    if data.get("status") != "ok":
        return pd.DataFrame(), {}
    iaqi = data["data"].get("iaqi", {})
    pm25 = iaqi.get("pm25", {}).get("v")
    df = pd.DataFrame([{
        "location": data["data"].get("city", {}).get("name", city),
        "pm25_latest_ugm3": pm25,
        "aqi_nowcast": pm25_to_aqi(pm25),
        "category": aqi_category(pm25_to_aqi(pm25)),
        "lat": data["data"]["city"]["geo"][0],
        "lon": data["data"]["city"]["geo"][1],
    }])
    return df, data

@st.cache_data(ttl=600)
def fetch_waqi_global(bounds="-180,-90,180,90"):
    """Fetch multiple stations in a bounding box"""
    url = f"https://api.waqi.info/map/bounds/?latlng={bounds}&token={WAQI_TOKEN}"
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    data = r.json()
    if data.get("status") != "ok":
        return pd.DataFrame()
    stations = []
    for s in data["data"]:
        pm25 = s.get("aqi")
        stations.append({
            "location": s.get("station", {}).get("name", "Unknown"),
            "pm25_latest_ugm3": pm25,
            "aqi_nowcast": pm25_to_aqi(int(pm25)) if str(pm25).isdigit() else None,
            "category": aqi_category(pm25_to_aqi(int(pm25)) if str(pm25).isdigit() else None),
            "lat": s.get("lat"),
            "lon": s.get("lon"),
        })
    return pd.DataFrame(stations)

# -------------------------
# Streamlit Modern Layout
# -------------------------
st.set_page_config(page_title="🌍 Fires & Air Quality Dashboard", layout="wide")
st.markdown(
    """
    <style>
    .main {background-color: #0e1117; color: white;}
    h1, h2, h3, h4 {color: #00ffcc;}
    .stDataFrame {background: #1c1f26;}
    </style>
    """, unsafe_allow_html=True
)

st.title("🌍 Wildfire & Air Quality Monitoring Dashboard")

# Sidebar Config
st.sidebar.header("Configuration")
mode = st.sidebar.radio("Air Quality Mode", ["City", "Global Bounding Box"])

if mode == "City":
    city = st.sidebar.text_input("Enter City", "Delhi")
    try:
        df_aq, _ = fetch_waqi_city(city)
        st.sidebar.success("✅ WAQI city data connected")
    except Exception as e:
        df_aq = pd.DataFrame()
        st.sidebar.error(f"WAQI city error: {e}")
else:
    west = st.sidebar.number_input("West (lon)", -180.0, 180.0, -125.0)
    south = st.sidebar.number_input("South (lat)", -90.0, 90.0, 32.0)
    east = st.sidebar.number_input("East (lon)", -180.0, 180.0, -114.0)
    north = st.sidebar.number_input("North (lat)", -90.0, 90.0, 42.0)
    bounds = f"{south},{west},{north},{east}"
    try:
        df_aq = fetch_waqi_global(bounds)
        st.sidebar.success("✅ WAQI global stations connected")
    except Exception as e:
        df_aq = pd.DataFrame()
        st.sidebar.error(f"WAQI global error: {e}")

try:
    df_fires = fetch_nasa_firms_global()
    st.sidebar.success("✅ NASA FIRMS connected")
except Exception as e:
    df_fires = pd.DataFrame()
    st.sidebar.error(f"NASA FIRMS error: {e}")

# -------------------------
# Dashboard Layout
# -------------------------
col1, col2 = st.columns(2)

with col1:
    st.subheader("🔥 Active Fires (NASA FIRMS)")
    if not df_fires.empty:
        st.map(df_fires.rename(columns={"latitude": "lat", "longitude": "lon"}))
        st.dataframe(df_fires.head(20))
    else:
        st.warning("No fire data available.")

with col2:
    st.subheader("🌫️ Air Quality — PM₂.₅ NowCast AQI")
    if not df_aq.empty:
        st.dataframe(df_aq)
        st.map(df_aq)
    else:
        st.warning("No air quality data available.")

