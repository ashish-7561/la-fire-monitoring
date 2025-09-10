import requests
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from geopy.distance import great_circle
import folium
from streamlit_folium import st_folium

# -------------------------
# Config
# -------------------------
WAQI_TOKEN = "3cd76abad0501e79bb285944bee4c559a17d69ba"

# -------------------------
# Utility & Analysis Functions
# -------------------------
def pm25_to_aqi(pm25_val):
    if pm25_val is None: return 0
    if 0 <= pm25_val <= 12.0: return round((50 - 0) / (12.0 - 0) * (pm25_val - 0) + 0)
    if 12.1 <= pm25_val <= 35.4: return round((100 - 51) / (35.4 - 12.1) * (pm25_val - 12.1) + 51)
    if 35.5 <= pm25_val <= 55.4: return round((150 - 101) / (55.4 - 35.5) * (pm25_val - 35.5) + 101)
    if 55.5 <= pm25_val <= 150.4: return round((200 - 151) / (150.4 - 55.5) * (pm25_val - 55.5) + 151)
    if 150.5 <= pm25_val <= 250.4: return round((300 - 201) / (250.4 - 150.5) * (pm25_val - 150.5) + 201)
    return 301

def analyze_fire_impact(city_coords, df_fires):
    if df_fires.empty or city_coords is None:
        return pd.DataFrame()
    
    impactful_fires = df_fires[df_fires['confidence'] > 80].copy()
    if impactful_fires.empty:
        return pd.DataFrame()

    city_lat, city_lon = city_coords
    impactful_fires['distance_km'] = impactful_fires.apply(
        lambda row: great_circle((city_lat, city_lon), (row['latitude'], row['longitude'])).kilometers,
        axis=1
    )
    
    nearby_fires = impactful_fires[impactful_fires['distance_km'] <= 500].sort_values(by='distance_km')
    
    return nearby_fires.head(10)

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
    url = f"https://api.waqi.info/feed/{city}/?token={WAQI_TOKEN}"
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    data = r.json()
    
    api_status = data.get("status")
    if api_status != "ok":
        return pd.DataFrame(), pd.DataFrame(), api_status, None
    
    city_coords = (data["data"]["city"]["geo"][0], data["data"]["city"]["geo"][1])
    pm25 = data["data"].get("iaqi", {}).get("pm25", {}).get("v")
    current_df = pd.DataFrame([{"location": data["data"].get("city", {}).get("name", city), "pm25_latest_ugm3": pm25, "lat": city_coords[0], "lon": city_coords[1]}])
    
    forecast_data = data["data"].get("forecast", {}).get("daily", {}).get("pm25", [])
    forecast_df = pd.DataFrame(forecast_data) if forecast_data else pd.DataFrame()
    if not forecast_df.empty: forecast_df['day'] = pd.to_datetime(forecast_df['day'])
        
    return current_df, forecast_df, api_status, city_coords

# -------------------------
# Visualization Functions
# -------------------------
def create_aqi_gauge(aqi_value):
    fig = go.Figure(go.Indicator(
        mode="gauge+number", value=aqi_value, title={'text': "Live Air Quality Index (AQI)"},
        gauge={'axis': {'range': [0, 301]}, 'bar': {'color': "black"},
               'steps': [{'range': [0, 50], 'color': "green"}, {'range': [51, 100], 'color': "yellow"}, {'range': [101, 150], 'color': "orange"},
                         {'range': [151, 200], 'color': "red"}, {'range': [201, 300], 'color': "purple"}, {'range': [301, 500], 'color': "maroon"}]}))
    fig.update_layout(height=250, margin=dict(l=10, r=10, t=40, b=10))
    return fig

def create_forecast_plot(df, city):
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df['day'], y=df['avg'], mode='lines+markers', name='Average Forecast'))
    fig.add_trace(go.Scatter(x=df['day'], y=df['max'], mode='lines', fill=None, line_color='lightgrey', name='Max'))
    fig.add_trace(go.Scatter(x=df['day'], y=df['min'], mode='lines', fill='tonexty', line_color='lightgrey', name='Min'))
    fig.update_layout(title=f"Live PM2.5 Forecast for {city}", xaxis_title="Date", yaxis_title="Predicted PM2.5", legend_title="Forecast")
    return fig

def create_interactive_fire_map(df_fires):
    fire_map = folium.Map(location=[20, 0], zoom_start=2, tiles="CartoDB dark_matter")
    df_plot = df_fires.sort_values(by='frp', ascending=False).head(500)
    for _, row in df_plot.iterrows():
        html = f"""<h4>Fire Hotspot Details</h4><p><b>Latitude:</b> {row['latitude']}<br><b>Longitude:</b> {row['longitude']}<br><b>Intensity (FRP):</b> {row['frp']}<br><b>Date Detected:</b> {row['acq_date']}</p>"""
        popup = folium.Popup(html, max_width=300)
        folium.CircleMarker(location=[row['latitude'], row['longitude']], radius=3, color='orangered', fill=True, fill_color='red', popup=popup).add_to(fire_map)
    return fire_map

# -------------------------
# Streamlit Layout
# -------------------------
st.set_page_config(page_title="🌍 Fires & Air Quality Dashboard", layout="wide")
st.title("🌍 Wildfire & Air Quality Monitoring Dashboard")

# --- Sidebar ---
st.sidebar.header("Configuration")
city = st.sidebar.text_input("Enter City", "Delhi")
city_coords = None

try:
    df_aq, df_forecast, api_status, city_coords = fetch_waqi_data(city)
    if api_status == "ok": st.sidebar.success("✅ WAQI data connected")
    else:
        st.sidebar.error("City not found by WAQI API.")
        df_aq, df_forecast = pd.DataFrame(), pd.DataFrame()
except Exception:
    df_aq, df_forecast = pd.DataFrame(), pd.DataFrame()
    st.sidebar.error(f"WAQI connection error.")

try:
    df_fires = fetch_nasa_firms_global()
    if not df_fires.empty: st.sidebar.success("✅ NASA FIRMS connected")
    else: st.sidebar.warning("NASA FIRMS: No fire data found.")
except Exception:
    df_fires = pd.DataFrame()
    st.sidebar.error(f"NASA FIRMS error.")

# --- Main Dashboard ---
col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("🔥 Active Fires (NASA FIRMS)")
    if not df_fires.empty:
        fire_map = create_interactive_fire_map(df_fires)
        st_folium(fire_map, use_container_width=True)
    else:
        st.warning("No significant fire data available in the last 7 days.")

with col2:
    st.subheader("🌫️ Air Quality — PM₂.₅ NowCast")
    if not df_aq.empty:
        pm25_value = df_aq['pm25_latest_ugm3'].iloc[0]
        aqi_value = pm25_to_aqi(pm25_value)
        st.plotly_chart(create_aqi_gauge(aqi_value), use_container_width=True)
        # --- THIS IS THE FIX ---
        st.map(df_aq) # This line adds the map back
    else:
        st.warning("No air quality data available.")

# --- Wildfire Impact Assessment Section ---
st.markdown("---")
st.header("🔬 Wildfire Impact Assessment")
impactful_fires_df = analyze_fire_impact(city_coords, df_fires)

if not impactful_fires_df.empty:
    closest_fire = impactful_fires_df.iloc[0]
    st.warning(f"**Alert:** Found {len(impactful_fires_df)} significant fire(s) within 500km. Closest fire is **{closest_fire['distance_km']:.0f} km** away.")
    st.write("Top 10 closest significant fires:")
    st.dataframe(impactful_fires_df[['latitude', 'longitude', 'distance_km', 'frp', 'acq_date']].rename(columns={'frp': 'Intensity (FRP)', 'acq_date': 'Date Acquired'}))
else:
    st.success("**Good news:** No significant fire activity detected within a 500km radius of the selected city.")

# --- Forecast Section ---
st.markdown("---")
st.header("🔮 Live 7-Day Air Quality Forecast")

if not df_forecast.empty:
    st.plotly_chart(create_forecast_plot(df_forecast, city), use_container_width=True)
else:
    st.warning("Forecast data is not available for this location.")
