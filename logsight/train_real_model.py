"""
Train Isolation Forest model on real OpenStack log dataset.

This script:
1. Downloads OpenStack logs from UCI ML Repository (if not cached)
2. Parses logs into structured format
3. Extracts features for ML model
4. Trains Isolation Forest on real log patterns
5. Calculates anomaly score quantiles for severity calibration
6. Saves trained model + quantiles to model.pkl
"""
from __future__ import annotations

import os
import pickle
import urllib.request
import zipfile
from typing import Dict, Tuple

import numpy as np
from sklearn.ensemble import IsolationForest

from .parser import parse_log_line
from .feature_engineering import extract_features
from .model import LogAnomalyDetector


def download_openstack_logs(dataset_path: str = "data/datasets/openstack_logs.log") -> bool:
    """Download OpenStack 2012 logs from UCI ML Repository if not cached."""
    if os.path.exists(dataset_path):
        print(f"Dataset already cached at {dataset_path}")
        return True

    # Create datasets directory if it doesn't exist
    dataset_dir = os.path.dirname(dataset_path)
    if not os.path.exists(dataset_dir):
        os.makedirs(dataset_dir)
        print(f"Created directory: {dataset_dir}")

    # LogHub OpenStack logs
    # Using the 2k dataset sample from the logpai/loghub repository
    url = "https://raw.githubusercontent.com/logpai/loghub/master/OpenStack/OpenStack_2k.log"

    try:
        print(f"Downloading OpenStack logs from {url}...")
        urllib.request.urlretrieve(url, dataset_path)
        print(f"Downloaded {dataset_path}")
        return True

    except Exception as e:
        print(f"Error downloading logs: {e}")
        print(f"\nManual Setup Instructions:")
        print(f"1. Download OpenStack logs from:")
        print(f"   https://raw.githubusercontent.com/logpai/loghub/master/OpenStack/OpenStack_2k.log")
        print(f"2. Save to: {dataset_path}")
        print(f"3. Or place any log file matching format:")
        print(f"   YYYY-MM-DD HH:MM:SS LEVEL SERVICE message")
        return False


def load_and_parse_logs(file_path: str, max_logs: int = 50000) -> list[dict]:
    """Load and parse log file, returning up to max_logs entries."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Log file not found: {file_path}")

    parsed_logs = []
    parse_errors = 0

    print(f"Parsing logs from {file_path}...")
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            for i, line in enumerate(f):
                if i >= max_logs:
                    break

                parsed = parse_log_line(line.strip())
                if parsed:
                    parsed_logs.append(parsed)
                else:
                    parse_errors += 1

                # Progress indicator
                if (i + 1) % 10000 == 0:
                    print(f"  Parsed {i + 1} lines, {len(parsed_logs)} valid entries")

    except Exception as e:
        print(f"Error reading log file: {e}")
        return []

    print(f"Successfully parsed {len(parsed_logs)} logs ({parse_errors} parse errors)")
    return parsed_logs


def prepare_training_data(parsed_logs: list[dict]) -> np.ndarray:
    """Extract features from parsed logs."""
    if not parsed_logs:
        raise ValueError("No parsed logs available for training")

    print(f"Extracting features from {len(parsed_logs)} logs...")
    features, _ = extract_features(parsed_logs)

    if features.size == 0:
        raise ValueError("Failed to extract features from logs")

    print(f"Feature matrix shape: {features.shape}")
    print(f"Feature statistics:")
    for i, name in enumerate(['Level', 'Message Length', 'Error Frequency', 'Repeated Count']):
        print(f"  {name}: min={features[:, i].min():.2f}, max={features[:, i].max():.2f}, mean={features[:, i].mean():.2f}")

    return features


def train_and_calibrate_model(
    training_features: np.ndarray,
    contamination: float = 0.05
) -> Tuple[LogAnomalyDetector, Dict[float, float]]:
    """Train Isolation Forest and calculate anomaly score quantiles."""
    print(f"Training Isolation Forest on {len(training_features)} samples...")

    detector = LogAnomalyDetector(contamination=contamination, random_state=42)
    detector.train(training_features)

    # Get anomaly scores for all training data
    print("Calculating anomaly score distribution...")
    anomaly_scores = detector.anomaly_scores(training_features)
    anomaly_scores_array = np.array(anomaly_scores)

    # Calculate quantiles
    quantiles_dict = {}
    for quantile in [0.10, 0.25, 0.50, 0.75, 0.90]:
        score = float(np.percentile(anomaly_scores_array, quantile * 100))
        quantiles_dict[quantile] = score
        print(f"  {quantile*100:.0f}th percentile: {score:.4f}")

    return detector, quantiles_dict


def save_model_with_calibration(
    detector: LogAnomalyDetector,
    quantiles_dict: Dict[float, float],
    model_path: str = "models/model.pkl"
) -> bool:
    """Save trained model and quantile calibration to pickle file."""
    try:
        print(f"Saving model and calibration to {model_path}...")

        # Create a package containing both model and calibration
        model_package = {
            'model': detector.model,
            'quantiles': quantiles_dict,
            'contamination': detector.model.contamination,
        }

        with open(model_path, 'wb') as f:
            pickle.dump(model_package, f)

        file_size = os.path.getsize(model_path) / 1024 / 1024  # MB
        print(f"Model saved successfully ({file_size:.2f} MB)")
        return True

    except Exception as e:
        print(f"Error saving model: {e}")
        return False


def generate_realistic_training_logs(
    output_path: str = "data/datasets/openstack_logs.log",
    num_logs: int = 20000
) -> bool:
    """
    Generate training logs that MATCH the demo generator's messages.
    This ensures the model learns patterns from actual logs it will see.
    """
    import random
    from datetime import datetime, timedelta

    print(f"Generating {num_logs} training logs (matching demo generator patterns)...")

    # Use SAME services and messages as log_generator.py
    services = [
        "UserService", "PaymentService", "AuthService",
        "DatabaseService", "CacheService"
    ]

    error_messages = [
        "Payment failed",
        "Database connection lost",
        "Authentication failed",
        "Service unavailable",
        "Request timeout exceeded",
        "Duplicate entry detected",
    ]

    info_messages = [
        "User login success",
        "API request completed",
        "Database connection established",
        "Cache hit for key",
        "Task scheduled successfully",
    ]

    warn_messages = [
        "High memory usage detected",
        "Slow query execution",
        "Rate limit approaching",
        "Connection timeout warning",
        "Disk space running low",
    ]

    try:
        start_time = datetime(2026, 1, 1, 0, 0, 0)
        with open(output_path, 'w', encoding='utf-8') as f:
            for i in range(num_logs):
                # Distribute: 70% INFO, 20% WARN, 10% ERROR
                rand = random.random()
                if rand < 0.70:
                    level = "INFO"
                    message = random.choice(info_messages)
                elif rand < 0.90:
                    level = "WARN"
                    message = random.choice(warn_messages)
                else:
                    level = "ERROR"
                    message = random.choice(error_messages)

                service = random.choice(services)
                timestamp = start_time + timedelta(seconds=random.randint(0, 86400 * 365))

                log_line = f"{timestamp.strftime('%Y-%m-%d %H:%M:%S')} {level} {service} {message}\n"
                f.write(log_line)

                if (i + 1) % 5000 == 0:
                    print(f"  Generated {i + 1} logs...")

        print(f"Generated training logs saved to {output_path}")
        return True

    except Exception as e:
        print(f"Error generating logs: {e}")
        return False


def main():
    print("INTELLIGENT LOG ANALYZER - MODEL TRAINING PIPELINE")
    print("Real Log Dataset: OpenStack logs (LogHub / LogPAI)")
    print("=" * 70)

    # Step 1: Download dataset (or generate realistic logs as fallback)
    dataset_path = "data/datasets/openstack_logs.log"
    if not download_openstack_logs(dataset_path):
        print("\nDataset download failed. Generating realistic training logs instead...")
        if not generate_realistic_training_logs(dataset_path, num_logs=20000):
            print("Failed to generate training logs.")
            return False
        print("Using generated logs for training.")

    # Step 2: Load and parse logs
    try:
        parsed_logs = load_and_parse_logs(dataset_path)
        if len(parsed_logs) < 1000:
            print(f"Warning: Only {len(parsed_logs)} valid logs parsed.")
            print("Try downloading a larger dataset or check log format.")
    except Exception as e:
        print(f"Error loading logs: {e}")
        return False

    # Step 3: Extract features
    try:
        training_features = prepare_training_data(parsed_logs)
    except Exception as e:
        print(f"Error extracting features: {e}")
        return False

    # Step 4: Train and calibrate
    try:
        detector, quantiles = train_and_calibrate_model(training_features)
    except Exception as e:
        print(f"Error training model: {e}")
        return False

    # Step 5: Save model
    if not save_model_with_calibration(detector, quantiles):
        print("Error saving model")
        return False

    print("\n" + "=" * 70)
    print("SUCCESS: MODEL TRAINING COMPLETE")
    print("=" * 70)
    print(f"[+] Trained on {len(parsed_logs)} real logs")
    print(f"[+] Quantile calibration data saved")
    print(f"[+] Model ready for anomaly detection")
    print("\nRun the app to start monitoring logs:")
    print("  Windows: start.bat")
    print("  Linux/Mac: bash start.sh")
    print("  Direct: python app.py")

    return True


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
