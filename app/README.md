🌍 Interactive Wildfire & Air Quality Monitoring Dashboard
# Live Demo Link : https://wildfire-air-quality-dashboard-paxcp2majwsaedsrlerdja.streamlit.app/

An advanced, interactive web dashboard built with Python and Streamlit to monitor environmental conditions globally. This tool provides a unified view of historical wildfire data and live air quality metrics, enhanced with interactive controls and live forecasting.
->✨ Key Features
Interactive Fire Map: Visualizes major historical wildfires on a global map with clickable popups showing details for each event (name, country, date, intensity).

Live Air Quality Monitoring: Fetches real-time air quality data for any city searched by the user from the World Air Quality Index (WAQI) API.

Dynamic AQI Gauge: Displays the current Air Quality Index (AQI) on a professional, color-coded gauge for immediate visual context.

Live 7-Day Forecasting: Provides an accurate 7-day air quality forecast for the selected city, pulled directly from the live WAQI forecast service.

Advanced Interactive Filters: Allows users to dynamically filter the wildfire data shown on the map by country and fire intensity, enabling powerful data exploration.

Robust Fallback System: Guarantees a functional and populated dashboard at all times. If a searched city is not found, it intelligently defaults to showing data for a major city.

Helpful AQI Guide: An expandable section in the sidebar explains the meaning of different AQI levels, making the data easy to understand for all users.

-> 🛠️ Technologies & Data Sources
Backend: Python

Web Framework: Streamlit

Data Manipulation: Pandas

Geospatial Analysis: Folium, Streamlit-Folium

Data Visualization: Plotly

Data Sources:

Live Air Quality & Forecast Data: World Air Quality Index (WAQI) API

Historical Wildfire Data: Curated dataset of major global fire events.

-> 🚀 Setup and Installation
To run this project locally, follow these steps:

Clone the repository:

git clone [https://github.com/ashish-7561/wildfire-air-quality-dashboard.git](https://github.com/ashish-7561/wildfire-air-quality-dashboard.git)
cd wildfire-air-quality-dashboard

Install the required libraries:

pip install -r requirements.txt

(Note: The requirements.txt in this repository is comprehensive. You may not need all packages for a minimal run.)

Run the Streamlit application:

streamlit run app/app_streamlit.py

The application will open in your web browser.
