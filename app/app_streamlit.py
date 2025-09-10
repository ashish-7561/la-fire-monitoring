import requests
import pandas as pd
import streamlit as st
import pickle
from prophet import Prophet
from prophet.plot import plot_plotly
import plotly.graph_objects as go

# -------------------------
# Config
# -------------------------
WAQI_TOKEN = "3cd76abad0501e79bb285944bee4c559a17d69ba"

# -------------------------
# Utility Functions
# -------------------------
def pm25_to_aqi(pm25_val):
    """Converts a PM2.5 value to the standard AQI value."""
    if pm25_val is None:
        return 0
    if 0 <= pm25_val <= 12.0:
        return round((50 - 0) / (12.0 - 0) * (pm25_val - 0) + 0)
    elif 12.1 <= pm25_val <= 35.4:
        return round((100 - 51) / (35.4 - 12.1) * (pm25_val - 12.1) + 51)
    elif 35.5 <= pm25_val <= 55.4:
        return round((150 - 101) / (55.4 - 35.5) * (pm25_val - 35.5) + 101)
    elif 55.5 <= pm25_val <= 150.4:
        return round((200 - 151) / (150.4 - 55.5) * (pm25_val - 55.5) + 151)
    elif 150.5 <= pm25_val <= 250.4:
        return round((300 - 201) / (250.4 - 150.5) * (pm25_val - 150.5) + 201)
    else: # Hazardous or beyond
        return 301 # Capping at 301+ for simplicity

# -------------------------
# Data Fetching
# -------------------------
@st.cache_data(ttl=3600)
def fetch_nasa_firms_global():
    VIIRS_URL = "https://firms.modaps.eosdis.nasa.gov/api/v1/fire/VIIRS_NOAA20_NRT/csv/world/7d"
    MODIS_URL = "https://firms.modaps.eosdis.nasa.gov/api/v1/fire/MODIS_NRT/csv/world/7d"
    try:
        df = pd.read_csv(VIIRS_URL)
        if not df.empty:
            return df
    except Exception:
        pass
    try:
        df = pd.read_csv(MODIS_URL)
        return df
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=600)
def fetch_waqi_city(city="Delhi"):
    url = f"https://api.waqi.info/feed/{city}/?token={WAQI_TOKEN}"
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    data = r.json()
    api_status = data.get("status")
    if api_status != "ok":
        return pd.DataFrame(), api_status
    
    iaqi = data["data"].get("iaqi", {})
    pm25 = iaqi.get("pm25", {}).get("v")
    
    df = pd.DataFrame([{
        "location": data["data"].get("city", {}).get("name", city),
        "pm25_latest_ugm3": pm25,
        "lat": data["data"]["city"]["geo"][0],
        "lon": data["data"]["city"]["geo"][1],
    }])
    return df, api_status

# -------------------------
# Visualization Functions
# -------------------------
def create_aqi_gauge(aqi_value):
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=aqi_value,
        title={'text': "Live Air Quality Index (AQI)"},
        gauge={
            'axis': {'range': [0, 301]},
            'bar': {'color': "black"},
            'steps': [
                {'range': [0, 50], 'color': "green"},
                {'range': [51, 100], 'color': "yellow"},
                {'range': [101, 150], 'color': "orange"},
                {'range': [151, 200], 'color': "red"},
                {'range': [201, 300], 'color': "purple"},
                {'range': [301, 500], 'color': "maroon"}],
        }))
    fig.update_layout(height=250, margin=dict(l=10, r=10, t=40, b=10))
    return fig

# -------------------------
# Forecasting Function
# -------------------------
@st.cache_resource
def load_forecast_model():
    try:
        with open("app/models/aqi_prophet_model.pkl", "rb") as f:
            model = pickle.load(f)
        return model
    except FileNotFoundError:
        return None

# -------------------------
# Streamlit Layout
# -------------------------
st.set_page_config(page_title="🌍 Fires & Air Quality Dashboard", layout="wide")
st.title("🌍 Wildfire & Air Quality Monitoring Dashboard")

# --- Sidebar ---
st.sidebar.header("Configuration")
city = st.sidebar.text_input("Enter City", "Delhi")

try:
    df_aq, api_status = fetch_waqi_city(city)
    if api_status == "ok":
        st.sidebar.success("✅ WAQI city data connected")
    else:
        st.sidebar.error("City not found by WAQI API. Please try a specific city name (e.g., Los Angeles).")
        df_aq = pd.DataFrame()
except Exception as e:
    df_aq = pd.DataFrame()
    st.sidebar.error(f"WAQI connection error: {e}")

try:
    df_fires = fetch_nasa_firms_global()
    if not df_fires.empty:
        st.sidebar.success("✅ NASA FIRMS connected")
    else:
        st.sidebar.warning("NASA FIRMS connected, but no fire data found.")
except Exception as e:
    df_fires = pd.DataFrame()
    st.sidebar.error(f"NASA FIRMS error: {e}")

# --- Main Dashboard ---
col1, col2 = st.columns(2)

with col1:
    st.subheader("🔥 Active Fires (NASA FIRMS)")
    if not df_fires.empty:
        st.map(df_fires.rename(columns={"latitude": "lat", "longitude": "lon"}))
    else:
        st.warning("No fire data available in the last 7 days from VIIRS or MODIS satellites.")

with col2:
    st.subheader("🌫️ Air Quality — PM₂.₅ NowCast")
    if not df_aq.empty:
        pm25_value = df_aq['pm25_latest_ugm3'].iloc[0]
        aqi_value = pm25_to_aqi(pm25_value)
        st.plotly_chart(create_aqi_gauge(aqi_value), use_container_width=True)
        st.map(df_aq)
    else:
        st.warning("No air quality data available.")

# --- Forecast Section ---
st.markdown("---")
st.header("🔮 7-Day Air Quality Forecast")
model = load_forecast_model()

if model is not None:
    st.success("✅ Forecast model loaded successfully!")
    future = model.make_future_dataframe(periods=7)
    forecast = model.predict(future)
    fig = plot_plotly(model, forecast)
    fig.update_layout(
        title=f"PM2.5 Forecast",
        xaxis_title="Date",
        yaxis_title="Predicted PM2.5"
    )
    st.plotly_chart(fig, use_container_width=True)
else:
    st.error("Forecast model file not found. Please ensure 'app/models/aqi_prophet_model.pkl' exists.")
