import pandas as pd
from prophet import Prophet
import pickle
from pathlib import Path

def train_and_save_model():
    """
    This function trains a Prophet forecasting model and saves it to a file.
    """
    # Create a directory to save our model
    Path("models").mkdir(exist_ok=True)

    # 1. Load the historical data
    print("Loading data from data/sample_aqi.csv...")
    df = pd.read_csv("data/sample_aqi.csv")

    # 2. Prepare the data for Prophet
    # Prophet requires columns 'ds' (datestamp) and 'y' (value)
    df_prophet = df.rename(columns={'Date': 'ds', 'PM2.5': 'y'})
    df_prophet['ds'] = pd.to_datetime(df_prophet['ds'])
    print("Data prepared for training.")

    # 3. Create and train the model
    print("Training the Prophet model...")
    model = Prophet()
    model.fit(df_prophet)
    print("Model training complete.")

    # 4. Save the trained model to a file
    model_path = "models/aqi_prophet_model.pkl"
    with open(model_path, "wb") as f:
        pickle.dump(model, f)
    
    print(f"Model successfully saved to {model_path}")

if __name__ == "__main__":
    train_and_save_model()
