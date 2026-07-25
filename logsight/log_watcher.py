"""Real-time log file watcher."""
from __future__ import annotations

import json
import os
import threading
import time
from typing import Callable, List, Optional

import numpy as np

from .alerts_storage import AlertsStorage
from .logs_storage import LogsStorage
from .feature_engineering import extract_features
from .model import LogAnomalyDetector, severity_from_anomaly_score
from .parser import parse_log_line


class LogWatcher:
    def __init__(
        self,
        log_file: str,
        model: LogAnomalyDetector,
        alerts_storage: AlertsStorage,
        logs_storage: LogsStorage,
        config: dict,
    ):
        self.log_file = log_file
        self.model = model
        self.alerts_storage = alerts_storage
        self.logs_storage = logs_storage
        self.config = config
        self.running = False
        self.thread: threading.Thread | None = None
        self.file_position = 0
        self.lock = threading.RLock()

    def start(self, check_interval: int = 1, start_at_end: bool = True) -> None:
        """Start watching the log file."""
        if self.running:
            return

        if start_at_end:
            self._seek_to_end()

        self.running = True
        self.thread = threading.Thread(target=self._run, args=(check_interval,), daemon=True)
        self.thread.start()

    def _run(self, check_interval: int) -> None:
        """Background thread that monitors the log file."""
        while self.running:
            try:
                self._check_new_lines()
                time.sleep(check_interval)
            except Exception as e:
                print(f"Error in log watcher: {e}")
                continue

    def _check_new_lines(self) -> None:
        """Read new lines from log file and process them."""
        if not os.path.exists(self.log_file):
            return

        with self.lock:
            try:
                # Reload config on each cycle to pick up mid-monitoring changes
                config_file = "config/config.json"
                if os.path.exists(config_file):
                    try:
                        with open(config_file, "r") as f:
                            self.config = json.load(f)
                    except (json.JSONDecodeError, IOError):
                        pass  # Keep using existing config if load fails

                with open(self.log_file, "r", encoding="utf-8") as f:
                    # Seek to last known position
                    f.seek(self.file_position)
                    new_lines = f.readlines()
                    self.file_position = f.tell()

                    if not new_lines:
                        return

                    # Parse and process new lines
                    self._process_new_logs(new_lines)
            except (IOError, OSError) as e:
                print(f"Error reading log file: {e}")

    def _process_new_logs(self, raw_lines: List[str]) -> None:
        """Parse and analyze new log lines."""
        # Parse raw lines
        parsed_logs = []
        for line in raw_lines:
            parsed = parse_log_line(line)
            if parsed:
                parsed_logs.append(parsed)

        if not parsed_logs:
            return

        # Determine which log levels to filter by
        custom_levels_str = self.config.get("custom_levels", "").strip()

        if custom_levels_str:
            # If custom levels provided, use ONLY those (ignore checkboxes)
            custom_levels = [
                level.strip().upper()
                for level in custom_levels_str.split(",")
                if level.strip()
            ]
            all_levels = custom_levels
        else:
            # Otherwise use the checkbox selections
            all_levels = self.config.get("log_levels", ["INFO", "WARN", "ERROR"])

        # Filter by log levels
        filtered_logs = [
            log for log in parsed_logs if log["level"] in all_levels
        ]

        if not filtered_logs:
            return

        # Filter by keywords if specified
        keywords = self.config.get("keywords", "")
        if keywords:
            keyword_list = [kw.strip().lower() for kw in keywords.split(",") if kw.strip()]
            if keyword_list:
                filtered_logs = [
                    log for log in filtered_logs
                    if any(kw in log["message"].lower() for kw in keyword_list)
                ]

        if not filtered_logs:
            return

        # Extract features and predict anomalies
        features, diagnostics = extract_features(filtered_logs)
        if features.size == 0:
            self.logs_storage.add_logs(filtered_logs)
            return

        # Store features for background retraining (Phase 3)
        self.logs_storage.add_features(features.tolist())

        try:
            self.model.predict(features)
            scores = self.model.anomaly_scores(features)
            logs_with_scores = []

            # Generate alerts for ALL logs with severity levels
            for log, score in zip(filtered_logs, scores):
                # Persist score with each log for dashboard display.
                log_with_score = dict(log)
                log_with_score["anomaly_score"] = round(float(score), 4)
                logs_with_scores.append(log_with_score)

                # Calculate severity for all logs (not just anomalies)
                severity = severity_from_anomaly_score(
                    score,
                    self.model.quantiles,
                    log_level=log.get("level", "INFO")
                )


                # Add all logs as alerts with their severity
                self.alerts_storage.add_alert(
                    service=log["service"],
                    severity=severity,
                    log_level=log["level"],
                    timestamp=log["timestamp"],
                    anomaly_score=score,
                    message=log.get("message", "")
                )

                # Print to console
                print(f"[{severity}] {log['service']} - {log['message']}")

            self.logs_storage.add_logs(logs_with_scores)
        except RuntimeError:
            # Model not trained yet
            self.logs_storage.add_logs(filtered_logs)

    def stop(self) -> None:
        """Stop watching the log file."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)

    def reset_position(self) -> None:
        """Reset file pointer to start of file."""
        with self.lock:
            self.file_position = 0

    def _seek_to_end(self) -> None:
        """Move file pointer to end so only new logs are processed."""
        if not os.path.exists(self.log_file):
            self.file_position = 0
            return
        with self.lock:
            try:
                with open(self.log_file, "rb") as f:
                    f.seek(0, os.SEEK_END)
                    self.file_position = f.tell()
            except (IOError, OSError):
                self.file_position = 0
