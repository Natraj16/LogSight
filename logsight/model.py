from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np
from sklearn.ensemble import IsolationForest


class LogAnomalyDetector:
    def __init__(self, contamination: float = 0.05, random_state: int = 42) -> None:
        self.model = IsolationForest(
            contamination=contamination,
            random_state=random_state,
            n_estimators=100,
        )
        self.is_trained = False
        self.quantiles = None  # Will be set from calibration data

    def train(self, training_features: np.ndarray) -> None:
        if training_features.size == 0:
            raise ValueError("Training features are empty.")

        self.model.fit(training_features)
        self.is_trained = True

    def predict(self, features: np.ndarray) -> List[int]:
        if not self.is_trained:
            raise RuntimeError("Model must be trained before prediction.")
        if features.size == 0:
            return []

        # IsolationForest returns -1 for anomalies, 1 for normal points.
        return self.model.predict(features).tolist()

    def anomaly_scores(self, features: np.ndarray) -> List[float]:
        if not self.is_trained:
            raise RuntimeError("Model must be trained before scoring.")
        if features.size == 0:
            return []

        # Lower scores indicate higher anomaly likelihood.
        return self.model.decision_function(features).tolist()

    def set_quantile_calibration(self, quantiles: Optional[dict]) -> None:
        """Set quantile thresholds for severity mapping."""
        self.quantiles = quantiles


def is_anomaly(score: float) -> bool:
    """Use the decision score as a lightweight anomaly gate."""
    return score < 0.0


def severity_from_anomaly_score(
    score: float,
    quantiles: Optional[Dict[float, float]],
    log_level: str = "INFO"
) -> str:
    """
    Map anomaly score to severity level using quantile calibration and explicit log level.
    """
    log_level = log_level.upper()
    
    # First priority: Explicit log levels
    if log_level in ["CRITICAL", "FATAL"]:
        return "Critical"
    elif log_level == "ERROR":
        return "High"
    elif log_level == "WARN":
        # Upgrade WARN if anomaly score is very low
        if quantiles and score < quantiles.get(0.25, float('-inf')):
            return "High"
        return "Medium"

    # Fallback if quantiles not available
    if quantiles is None:
        return "Low"

    # Pure model-based severity mapping (no domain rules)
    if score < quantiles.get(0.10, float('-inf')):
        return "Critical"
    elif score < quantiles.get(0.25, float('-inf')):
        return "High"
    elif score < quantiles.get(0.50, float('-inf')):
        return "Medium"
    else:
        return "Low"

def retrain_model(
    logs_storage,
    contamination: float = 0.1,
    min_samples: int = 50,
    model_dir: str = "models",
):
    import os
    import pickle
    from datetime import datetime
    
    X = logs_storage.get_recent_features(limit=5000)
    if not X or len(X) < min_samples:
        return None
        
    X_arr = np.array(X, dtype=float)
    model = IsolationForest(contamination=contamination, random_state=42, n_estimators=100)
    model.fit(X_arr)
    
    os.makedirs(model_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    model_path = os.path.join(model_dir, f"model_{timestamp}.pkl")
    
    with open(model_path, "wb") as f:
        pickle.dump(model, f)
        
    # Overwrite the active one for next cold start
    with open(os.path.join(model_dir, "model.pkl"), "wb") as f:
        pickle.dump(model, f)
        
    return model

class ModelRetrainer:
    def __init__(
        self,
        detector: LogAnomalyDetector,
        logs_storage,
        interval_minutes: int = 5,
        min_samples: int = 50
    ):
        self.detector = detector
        self.logs_storage = logs_storage
        self.interval_minutes = interval_minutes
        self.min_samples = min_samples
        self.running = False
        self.thread = None
        
    def start(self):
        import threading
        if self.running: return
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        
    def stop(self):
        self.running = False
        
    def _run(self):
        import time
        from datetime import datetime
        while self.running:
            time.sleep(self.interval_minutes * 60)
            if not self.running:
                break
            try:
                new_model = retrain_model(
                    self.logs_storage,
                    min_samples=self.min_samples
                )
                if new_model:
                    self.detector.model = new_model
                    self.detector.is_trained = True
                    print(f"[{datetime.now().isoformat()}] ModelRetrainer: Successfully retrained model with real data.")
            except Exception as e:
                print(f"ModelRetrainer Error: {e}")
