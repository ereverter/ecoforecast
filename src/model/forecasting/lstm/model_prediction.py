"""
Script to make predictions using an LSTM trained model for forecasting.
"""
# General imports
import argparse
import joblib
import json
import os

# Data related imports
import numpy as np
import torch

# Local imports
from src.definitions import (
    PREDICTIONS_DIR,
    MODELS_DIR,
    LSTM_LAGS,
)
from src.data.prepare_data import load_data
from src.model.forecasting.lstm.model_training import (
    prepare_data, 
    create_sequences, 
    LSTMModel,
)

### GENERAL FUNCTIONS ###

def load_model(model_path, input_size):
    # Model configuration
    CONFIG_PATH = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'model_config.json')
    with open(CONFIG_PATH, 'r') as f:
        model_config = json.load(f)  # LSTM configuration

    model = LSTMModel(input_size, model_config['hidden_layer_size'])
    model.load_state_dict(torch.load(model_path))
    model.eval()  # Set the model to evaluation mode
    return model

### MAIN ###

def main():
    parser = argparse.ArgumentParser(description='Make predictions using LSTM')
    parser.add_argument('--model', type=str, help='Path to model')
    parser.add_argument('--data', type=str, help='Path to prediction data')
    args = parser.parse_args()

    # Load and prepare prediction data
    _, validation = load_data()
    validation = prepare_data(validation)
    x_predict, _ = create_sequences(validation.drop(['timestamp', 'series_id'], axis=1), lags=LSTM_LAGS)
    
    # Load the saved scalers
    x_scaler_path = os.path.join(MODELS_DIR, 'forecasting/lstm', 'x_scaler.pkl')
    x_scaler = joblib.load(x_scaler_path)

    # Normalize x_predict using the loaded scaler
    x_predict_scaled = x_scaler.transform(x_predict.reshape(-1, x_predict.shape[2]))
    x_predict_scaled = x_predict_scaled.reshape(-1, LSTM_LAGS, x_predict.shape[2])

    # Convert to PyTorch tensor
    x_predict_tensor = torch.tensor(x_predict_scaled, dtype=torch.float32)

    model_path = args.model
    input_size = x_predict.shape[2]
    model = load_model(model_path, input_size)

    # Make predictions
    with torch.no_grad():
        predictions = model(x_predict_tensor).numpy()

    y_scaler_path = os.path.join(MODELS_DIR, 'forecasting/lstm', 'y_scaler.pkl')
    y_scaler = joblib.load(y_scaler_path)
    predictions = y_scaler.inverse_transform(predictions)

    # Ignore first LSTM_LAGS rows of validation by adding LSTM_LAGS nan predictions with (n, 1) shape
    predictions = np.concatenate([np.full((LSTM_LAGS, 1), np.nan), predictions])

    # Convert predictions back to original format
    validation['predicted_surplus'] = predictions
    pivoted_df = validation.pivot(index='timestamp', columns='series_id', values='predicted_surplus')

    # Get the maximum country code for each row (timestamp)
    max_col = pivoted_df.idxmax(axis=1)
    pivoted_df['target'] = max_col

    predictions_path = os.path.join(PREDICTIONS_DIR, 'lstm_predictions.json')
    pivoted_df.reset_index()[['timestamp', 'target']].to_json(predictions_path, orient='records')

    print(f"Predictions saved to {predictions_path}")

if __name__ == "__main__":
    main()
