import pytest
import numpy as np
from logsight.model import LogAnomalyDetector, retrain_model

class DummyStorage:
    def __init__(self, data):
        self.data = data
    def get_recent_features(self, limit=5000):
        return self.data

def test_model_retraining_trigger(tmp_path):
    # Provide 49 samples
    features_small = np.random.rand(49, 10).tolist()
    storage_small = DummyStorage(features_small)
    
    # Should return None because len < min_samples
    model_small = retrain_model(storage_small, min_samples=50, model_dir=str(tmp_path))
    assert model_small is None
    
    # Provide 51 samples
    features_large = np.random.rand(51, 10).tolist()
    storage_large = DummyStorage(features_large)
    
    model_large = retrain_model(storage_large, min_samples=50, model_dir=str(tmp_path))
    assert model_large is not None
