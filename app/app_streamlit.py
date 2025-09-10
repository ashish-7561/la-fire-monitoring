import requests
import pandas as pd
import streamlit as st
import pickle
from prophet import Prophet
from prophet.plot import plot_plotly

# -------------------------
# Config
# -------------------------
WAQI_TOKEN = "3cd76abad0501e79bb285944bee4c559a17d69ba"

# -------------------------
# Data Fetching
# -------------------------
@st.cache_data(ttl=3600)
def fetch_nasa_firms_global():
    """
    Fetches global fire data, trying the primary VIIRS satellite first
    and falling back to the MODIS satellite if the first is empty or fails.
    We use the 7-day feed to increase the chance of seeing data.
    """
    VIIRS_URL = "https://firms.modaps.eosdis.nasa.gov/api/v1/fire/VIIRS_NOAA20_NRT/csv/world/7d"
    MODIS_URL = "https://firms.modaps.eosdis.nasa.gov/api/v1/fire/MODIS_NRT/csv/world/7d"
    
    try:
        # Try the primary, higher-resolution satellite first
        df = pd.read_csv(VIIRS_URL)
        if not df.empty:
            return df
    except Exception:
        # If the primary URL fails, we'll try the fallback
        pass
        
    # If the primary source was empty or failed, try the fallback satellite
    try:
        df = pd.read_csv(MODIS_URL)
        return df
    except Exception:
        # If both fail, return an empty dataframe
        return pd.DataFrame()

@st.cache_data(ttl=600)
def fetch_waqi_city(city="Delhi"):
    url = f"https://api.waqi.info/feed/{city}/?token={WAQI_TOKEN}"
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    data = r.json()
    if data.get("status") != "ok":
        return pd.DataFrame()
    
    iaqi = data["data"].get("iaqi", {})
    pm25 = iaqi.get("pm25", {}).get("v")
    
    df = pd.DataFrame([{
        "location": data["data"].get("city", {}).get("name", city),
        "pm25_latest_ugm3": pm25,
        "lat": data["data"]["city"]["geo"][0],
        "lon": data["data"]["city"]["geo"][1],
    }])
    return df

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
    df_aq = fetch_waqi_city(city)
    st.sidebar.success("✅ WAQI city data connected")
except Exception as e:
    df_aq = pd.DataFrame()
    st.sidebar.error(f"WAQI city error: {e}")

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
        st.dataframe(df_aq)
        st.map(df_aq)
    else:
        st.warning("No air quality data available.")

# --- NEW: Forecast Section ---
st.markdown("---")
st.header("🔮 7-Day Air Quality Forecast")

model = load_forecast_model()

if model is not None:
    st.success("✅ Forecast model loaded successfully!")
    
    # Make prediction
    future = model.make_future_dataframe(periods=7)
    forecast = model.predict(future)

    # Display plot
    fig = plot_plotly(model, forecast)
    fig.update_layout(
        title=f"PM2.5 Forecast for {city}",
        xaxis_title="Date",
        yaxis_title="Predicted PM2.5"
    )
    st.plotly_chart(fig, use_container_width=True)
    
    # Display forecast data
    st.write("Forecast Data:")
    st.dataframe(forecast[['ds', 'yhat', 'yhat_lower', 'yhat_upper']].tail(7))
else:
    st.error("Forecast model file not found. Please ensure 'app/models/aqi_prophet_model.pkl' exists.")
