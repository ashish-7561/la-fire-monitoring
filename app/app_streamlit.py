import requests
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
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
    if pm25_val is None: return 0, "Unknown"
    aqi = 0
    if 0 <= pm25_val <= 12.0: aqi = round((50 - 0) / (12.0 - 0) * (pm25_val - 0) + 0)
    elif 12.1 <= pm25_val <= 35.4: aqi = round((100 - 51) / (35.4 - 12.1) * (pm25_val - 12.1) + 51)
    elif 35.5 <= pm25_val <= 55.4: aqi = round((150 - 101) / (55.4 - 35.5) * (pm25_val - 35.5) + 101)
    elif 55.5 <= pm25_val <= 150.4: aqi = round((200 - 151) / (150.4 - 55.5) * (pm25_val - 55.5) + 151)
    elif 150.5 <= pm25_val <= 250.4: aqi = round((300 - 201) / (250.4 - 150.5) * (pm25_val - 150.5) + 201)
    else: aqi = 301
    
    if aqi <= 50: category = "Good"
    elif aqi <= 100: category = "Moderate"
    elif aqi <= 150: category = "Unhealthy for Sensitive Groups"
    elif aqi <= 200: category = "Unhealthy"
    elif aqi <= 300: category = "Very Unhealthy"
    else: category = "Hazardous"
    return aqi, category

# -------------------------
# Data Fetching
# -------------------------
@st.cache_data
def load_historical_fires():
    """Loads a curated list of major historical wildfires."""
    try:
        df = pd.read_csv("app/data/major_wildfires.csv")
        return df
    except FileNotFoundError:
        return pd.DataFrame()

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
    
    pm25 = data["data"].get("iaqi", {}).get("pm25", {}).get("v")
    current_df = pd.DataFrame([{"location": data["data"].get("city", {}).get("name", city), "pm25_latest_ugm3": pm25, "lat": data["data"]["city"]["geo"][0], "lon": data["data"]["city"]["geo"][1]}])
    
    forecast_data = data["data"].get("forecast", {}).get("daily", {}).get("pm25", [])
    forecast_df = pd.DataFrame(forecast_data) if forecast_data else pd.DataFrame()
    if not forecast_df.empty: forecast_df['day'] = pd.to_datetime(forecast_df['day'])
        
    return current_df, forecast_df, api_status

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
    for _, row in df_fires.iterrows():
        html = f"""<h4>{row['name']}</h4><p><b>Country:</b> {row['country']}<br><b>Date:</b> {row['start_date']}<br><b>Intensity (FRP):</b> {row['intensity_frp']}</p>"""
        popup = folium.Popup(html, max_width=300)
        folium.CircleMarker(location=[row['latitude'], row['longitude']], radius=5, color='orangered', fill=True, fill_color='red', popup=popup).add_to(fire_map)
    return fire_map

# -------------------------
# Streamlit Layout
# -------------------------
st.set_page_config(page_title="🌍 Fires & Air Quality Dashboard", layout="wide")
st.title("🌍 Wildfire & Air Quality Monitoring Dashboard")

# --- Data Loading ---
df_fires = load_historical_fires()

# --- Sidebar ---
st.sidebar.header("Configuration")
st.sidebar.subheader("Air Quality Search")
city = st.sidebar.text_input("Enter City", "Delhi")

# --- Fire Data Filtering Controls ---
st.sidebar.subheader("Fire Map Filters")
if not df_fires.empty:
    country_list = ['All'] + sorted(df_fires['country'].unique())
    selected_countries = st.sidebar.multiselect("Select Country/Countries", country_list, default=['All'])
    
    min_intensity, max_intensity = int(df_fires['intensity_frp'].min()), int(df_fires['intensity_frp'].max())
    selected_intensity = st.sidebar.slider("Minimum Fire Intensity (FRP)", min_intensity, max_intensity, min_intensity)
    
    # Apply filters
    if 'All' not in selected_countries:
        df_fires_filtered = df_fires[df_fires['country'].isin(selected_countries)]
    else:
        df_fires_filtered = df_fires.copy()
    
    df_fires_filtered = df_fires_filtered[df_fires_filtered['intensity_frp'] >= selected_intensity]
else:
    st.sidebar.warning("Fire data not loaded.")
    df_fires_filtered = pd.DataFrame()

# --- NEW: AQI Levels Guide ---
st.sidebar.subheader("Reference")
with st.sidebar.expander("What do the AQI levels mean?"):
    st.markdown("""
    - **🟢 Good (0-50):** Air quality is satisfactory, and air pollution poses little or no risk.
    - **🟡 Moderate (51-100):** Air quality is acceptable. However, there may be a risk for some people, particularly those who are unusually sensitive to air pollution.
    - **🟠 Unhealthy for Sensitive Groups (101-150):** Members of sensitive groups may experience health effects. The general public is less likely to be affected.
    - **🔴 Unhealthy (151-200):** Some members of the general public may experience health effects; members of sensitive groups may experience more serious health effects.
    - **🟣 Very Unhealthy (201-300):** Health alert: The risk of health effects is increased for everyone.
    - **🟤 Hazardous (301+):** Health warning of emergency conditions: everyone is more likely to be affected.
    """)

# --- Data Loading with Fallback Logic for AQI ---
show_fallback_message = False
try:
    df_aq, df_forecast, api_status = fetch_waqi_data(city)
    if api_status != "ok":
        show_fallback_message = True
        df_aq, df_forecast, api_status = fetch_waqi_data("Delhi") # Fallback
except Exception:
    show_fallback_message = True
    df_aq, df_forecast, api_status = fetch_waqi_data("Delhi") # Fallback
    st.sidebar.error("Could not connect to live AQI data.")

if show_fallback_message:
    st.info(f"Could not find live data for '{city}'. Showing results for Delhi instead.", icon="ℹ️")

# --- Main Dashboard ---
col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("Major Historical Wildfires")
    if not df_fires_filtered.empty:
        fire_map = create_interactive_fire_map(df_fires_filtered)
        st_folium(fire_map, use_container_width=True, height=450)
    else:
        st.warning("No historical fire data matches your filter criteria.")

with col2:
    st.subheader("🌫️ Air Quality — PM₂.₅ NowCast")
    if not df_aq.empty:
        pm25_value = df_aq['pm25_latest_ugm3'].iloc[0]
        aqi_value, aqi_category = pm25_to_aqi(pm25_value)
        st.plotly_chart(create_aqi_gauge(aqi_value), use_container_width=True)
        st.map(df_aq)
    else:
        st.warning("No air quality data available.")

# --- Forecast Section ---
st.markdown("---")
st.header("🔮 Live 7-Day Air Quality Forecast")

if not df_forecast.empty:
    display_city = df_aq['location'].iloc[0] if not df_aq.empty else city
    st.plotly_chart(create_forecast_plot(df_forecast, display_city), use_container_width=True)
else:
    st.warning("Forecast data is not available for this location.")
