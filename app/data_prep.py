# data_prep.py
import pandas as pd
from pathlib import Path

def create_sample_aqi(path='data/sample_aqi.csv'):
    df = pd.read_csv(path, parse_dates=['date'])
    # basic cleaning example:
    df = df.sort_values('date')
    df = df.fillna(method='ffill')
    df.to_csv(path, index=False)
    print("Sample AQI ready:", path)

if __name__ == "__main__":
    Path('data').mkdir(exist_ok=True)
    # if sample not present, create default file:
    sample = Path('data/sample_aqi.csv')
    if not sample.exists():
        sample_text = """date,location,aqi,pm25,pm10,no2,so2,co,temp,humidity
2025-01-01,LA,85,40,60,20,5,0.7,15.2,56
2025-01-02,LA,110,55,80,35,8,1.0,14.8,52
2025-01-03,LA,140,85,110,50,10,1.3,13.5,49
2025-01-04,LA,160,100,130,60,13,1.6,12.4,45
2025-01-05,LA,95,45,70,22,6,0.8,16.0,58
"""
        sample.write_text(sample_text)
    create_sample_aqi()
