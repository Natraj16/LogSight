from __future__ import annotations

from collections import Counter
from typing import Dict, List, Tuple

import numpy as np

LEVEL_MAP = {
    "DEBUG": 0,
    "INFO": 0,
    "WARN": 1,
    "WARNING": 1,
    "ERROR": 2,
    "CRITICAL": 3,
    "FATAL": 3,
}


def _rolling_error_count(levels: List[str], index: int, window_size: int) -> int:
    start = max(0, index - window_size + 1)
    return sum(1 for level in levels[start : index + 1] if level == "ERROR")


def extract_features(
    parsed_logs: List[Dict[str, str]],
    recent_window: int = 10,
) -> Tuple[np.ndarray, List[Dict[str, int]]]:
    """Convert parsed logs into model features and extra diagnostics."""
    if not parsed_logs:
        return np.empty((0, 4), dtype=float), []

    levels = [entry["level"] for entry in parsed_logs]
    message_counts = Counter(entry["message"] for entry in parsed_logs)

    feature_rows: List[List[float]] = []
    diagnostics: List[Dict[str, int]] = []

    for index, entry in enumerate(parsed_logs):
        level_value = LEVEL_MAP.get(entry["level"], 0)
        message_length = len(entry["message"])
        error_frequency = _rolling_error_count(levels, index, recent_window)
        repeated_message_count = message_counts[entry["message"]]

        feature_rows.append(
            [
                float(level_value),
                float(message_length),
                float(error_frequency),
                float(repeated_message_count),
            ]
        )
        diagnostics.append(
            {
                "error_frequency": error_frequency,
                "repeated_message_count": repeated_message_count,
            }
        )

    return np.array(feature_rows, dtype=float), diagnostics
