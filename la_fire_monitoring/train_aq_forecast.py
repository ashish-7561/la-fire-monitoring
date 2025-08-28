# train_aq_forecast.py
import pandas as pd
import numpy as np
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import LSTM, Dense
from sklearn.preprocessing import MinMaxScaler
import matplotlib.pyplot as plt

def load_data(path='data/sample_aqi.csv'):
    df = pd.read_csv(path, parse_dates=['date'])
    df = df.sort_values('date')
    return df

def make_sequences(values, seq_len=3):
    X, y = [], []
    for i in range(len(values)-seq_len):
        X.append(values[i:i+seq_len])
        y.append(values[i+seq_len])
    return np.array(X), np.array(y)

def train(path='data/sample_aqi.csv'):
    df = load_data(path)
    values = df['aqi'].values.reshape(-1,1)
    scaler = MinMaxScaler()
    scaled = scaler.fit_transform(values)
    seq_len = 3
    X, y = make_sequences(scaled, seq_len)
    X = X.reshape((X.shape[0], X.shape[1], 1))

    model = Sequential([
        LSTM(32, input_shape=(seq_len,1)),
        Dense(1)
    ])
    model.compile(optimizer='adam', loss='mse')
    model.fit(X, y, epochs=100, verbose=1)

    # save model
    model.save('models/aqi_lstm.h5')
    print("Saved model to models/aqi_lstm.h5")
    return model, scaler

if __name__ == "__main__":
    import os
    os.makedirs('models', exist_ok=True)
    train()
