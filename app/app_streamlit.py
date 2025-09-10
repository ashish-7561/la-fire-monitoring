import requests
import pandas as pd
import streamlit as st
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
    if pm25_val is None: return 0
    if 0 <= pm25_val <= 12.0: return round((50 - 0) / (12.0 - 0) * (pm25_val - 0) + 0)
    if 12.1 <= pm25_val <= 35.4: return round((100 - 51) / (35.4 - 12.1) * (pm25_val - 12.1) + 51)
    if 35.5 <= pm25_val <= 55.4: return round((150 - 101) / (55.4 - 35.5) * (pm25_val - 35.5) + 101)
    if 55.5 <= pm25_val <= 150.4: return round((200 - 151) / (150.4 - 55.5) * (pm25_val - 55.5) + 151)
    if 150.5 <= pm25_val <= 250.4: return round((300 - 201) / (250.4 - 150.5) * (pm25_val - 150.5) + 201)
    return 301

# -------------------------
# Data Fetching
# -------------------------
@st.cache_data(ttl=3600)
def fetch_nasa_firms_global():
    VIIRS_URL = "https://firms.modaps.eosdis.nasa.gov/api/v1/fire/VIIRS_NOAA20_NRT/csv/world/7d"
    MODIS_URL = "https://firms.modaps.eosdis.nasa.gov/api/v1/fire/MODIS_NRT/csv/world/7d"
    try:
        df = pd.read_csv(VIIRS_URL)
        if not df.empty: return df
    except Exception: pass
    try:
        df = pd.read_csv(MODIS_URL)
        return df
    except Exception: return pd.DataFrame()

@st.cache_data(ttl=600)
def fetch_waqi_data(city="Delhi"):
    """Fetches both current and forecast data from the WAQI API."""
    url = f"https://api.waqi.info/feed/{city}/?token={WAQI_TOKEN}"
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    data = r.json()
    
    api_status = data.get("status")
    if api_status != "ok":
        return pd.DataFrame(), pd.DataFrame(), api_status
    
    # Parse current data
    iaqi = data["data"].get("iaqi", {})
    pm25 = iaqi.get("pm25", {}).get("v")
    current_df = pd.DataFrame([{
        "location": data["data"].get("city", {}).get("name", city),
        "pm25_latest_ugm3": pm25,
        "lat": data["data"]["city"]["geo"][0],
        "lon": data["data"]["city"]["geo"][1],
    }])
    
    # Parse forecast data
    forecast_data = data["data"].get("forecast", {}).get("daily", {}).get("pm25", [])
    if forecast_data:
        forecast_df = pd.DataFrame(forecast_data)
        forecast_df['day'] = pd.to_datetime(forecast_df['day'])
    else:
        forecast_df = pd.DataFrame()
        
    return current_df, forecast_df, api_status

# -------------------------
# Visualization Functions
# -------------------------
def create_aqi_gauge(aqi_value):
    fig = go.Figure(go.Indicator(
        mode="gauge+number", value=aqi_value, title={'text': "Live Air Quality Index (AQI)"},
        gauge={
            'axis': {'range': [0, 301]}, 'bar': {'color': "black"},
            'steps': [
                {'range': [0, 50], 'color': "green"}, {'range': [51, 100], 'color': "yellow"},
                {'range': [101, 150], 'color': "orange"}, {'range': [151, 200], 'color': "red"},
                {'range': [201, 300], 'color': "purple"}, {'range': [301, 500], 'color': "maroon"}],
        }))
    fig.update_layout(height=250, margin=dict(l=10, r=10, t=40, b=10))
    return fig

def create_forecast_plot(df, city):
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df['day'], y=df['avg'], mode='lines+markers', name='Average Forecast'))
    fig.add_trace(go.Scatter(x=df['day'], y=df['max'], mode='lines', fill=None, line_color='lightgrey', name='Max'))
    fig.add_trace(go.Scatter(x=df['day'], y=df['min'], mode='lines', fill='tonexty', line_color='lightgrey', name='Min'))
    fig.update_layout(
        title=f"Live PM2.5 Forecast for {city}",
        xaxis_title="Date", yaxis_title="Predicted PM2.5",
        legend_title="Forecast"
    )
    return fig

# -------------------------
# Streamlit Layout
# -------------------------
st.set_page_config(page_title="🌍 Fires & Air Quality Dashboard", layout="wide")
st.title("🌍 Wildfire & Air Quality Monitoring Dashboard")

# --- Sidebar ---
st.sidebar.header("Configuration")
city = st.sidebar.text_input("Enter City", "Delhi")

try:
    df_aq, df_forecast, api_status = fetch_waqi_data(city)
    if api_status == "ok":
        st.sidebar.success("✅ WAQI data connected")
    else:
        st.sidebar.error("City not found by WAQI API. Please try a specific city name (e.g., Los Angeles).")
        df_aq = pd.DataFrame()
        df_forecast = pd.DataFrame()
except Exception as e:
    df_aq, df_forecast = pd.DataFrame(), pd.DataFrame()
    st.sidebar.error(f"WAQI connection error: {e}")

try:
    df_fires = fetch_nasa_firms_global()
    if not df_fires.empty: st.sidebar.success("✅ NASA FIRMS connected")
    else: st.sidebar.warning("NASA FIRMS connected, but no fire data found.")
except Exception as e:
    df_fires, df_forecast = pd.DataFrame(), pd.DataFrame()
    st.sidebar.error(f"NASA FIRMS error: {e}")

# --- Main Dashboard ---
col1, col2 = st.columns(2)

with col1:
    st.subheader("🔥 Active Fires (NASA FIRMS)")
    if not df_fires.empty: st.map(df_fires.rename(columns={"latitude": "lat", "longitude": "lon"}))
    else: st.warning("No fire data available in the last 7 days from VIIRS or MODIS satellites.")

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
st.header("🔮 Live 7-Day Air Quality Forecast")

if not df_forecast.empty:
    st.plotly_chart(create_forecast_plot(df_forecast, city), use_container_width=True)
else:
    st.warning("Forecast data is not available for this location.")
