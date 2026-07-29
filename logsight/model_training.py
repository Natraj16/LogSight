"""ML model initialization and training."""
from __future__ import annotations

import os
import pickle
from typing import Optional

import numpy as np

from .model import LogAnomalyDetector


import os
DEFAULT_MODEL_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models", "model.pkl")

def load_or_train_model(model_path: str = DEFAULT_MODEL_PATH) -> LogAnomalyDetector:
    """Load model from pickle or train new one if not found."""
    detector = LogAnomalyDetector()

    if os.path.exists(model_path):
        try:
            with open(model_path, "rb") as f:
                model_data = pickle.load(f)

                # Handle new format (with quantiles) vs old format (just model)
                if isinstance(model_data, dict) and 'model' in model_data:
                    # New format: trained on real data with calibration
                    detector.model = model_data['model']
                    detector.quantiles = model_data.get('quantiles')
                    detector.is_trained = True
                    print(f"Loaded pre-trained model from {model_path}")
                    if detector.quantiles:
                        print(f"Quantile calibration loaded: {len(detector.quantiles)} percentiles")
                else:
                    # Old format: just the model object
                    detector.model = model_data
                    detector.is_trained = True
                    print(f"Loaded legacy model from {model_path}")

                return detector
        except Exception as e:
            print(f"Error loading model: {e}. Training new model.")

    # Train on dummy data as fallback
    print("Training model on dummy data...")
    dummy_features = _generate_dummy_training_data()
    detector.train(dummy_features)

    # Save model
    try:
        with open(model_path, "wb") as f:
            pickle.dump(detector.model, f)
        print(f"Model trained and saved to {model_path}")
    except Exception as e:
        print(f"Error saving model: {e}")

    return detector


def _generate_dummy_training_data(num_samples: int = 100) -> np.ndarray:
    """Generate dummy training data for initial model training."""
    np.random.seed(42)

    # Generate synthetic features: [level_value, message_length, error_frequency, repeated_message_count]
    level_values = np.random.choice([0, 1, 2], size=num_samples, p=[0.6, 0.3, 0.1])
    message_lengths = np.random.normal(50, 30, num_samples)
    error_frequencies = np.random.choice([0, 1, 2, 3, 4, 5], size=num_samples)
    repeated_counts = np.random.choice([1, 2, 3, 4, 5], size=num_samples)

    # Ensure no negative values
    message_lengths = np.maximum(message_lengths, 10)

    features = np.column_stack([
        level_values,
        message_lengths,
        error_frequencies,
        repeated_counts,
    ])

    return features.astype(float)
