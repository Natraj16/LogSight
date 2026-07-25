"""Module for wrapping user process and monitoring stdout/stderr."""
import json
import os
import subprocess
import threading
from typing import Any, List

import numpy as np

from .alerts_storage import AlertsStorage
from .logs_storage import LogsStorage
from .parser import parse_log_line
from .feature_engineering import extract_features
from .model import severity_from_anomaly_score


class ProcessWrapper:
    def __init__(self, command: List[str], model, alerts_storage: AlertsStorage, logs_storage: LogsStorage, config: dict[str, Any]):
        if command and command[0] in ("python", "python3") and "-u" not in command:
            command.insert(1, "-u")
        self.command = command
        self.model = model
        self.alerts_storage = alerts_storage
        self.logs_storage = logs_storage
        self.config = config
        self.process: subprocess.Popen | None = None
        self._thread: threading.Thread | None = None
        self.running = False
        self._buffer: list = []
        self._buffer_lock = threading.Lock()

    def _save_config(self):
        """Save this run configuration."""
        config_dir = ".log-analyzer"
        if not os.path.exists(config_dir):
            os.makedirs(config_dir)
            try:
                with open(os.path.join(config_dir, ".gitignore"), "w") as gf:
                    gf.write("*.db\n*.db-journal\n*.db-wal\nconfig.json\n")
            except IOError:
                pass
        config_path = os.path.join(config_dir, "config.json")
        try:
            with open(config_path, "w") as f:
                json.dump({"command": self.command, **self.config}, f, indent=2)
        except IOError:
            pass

    def start(self):
        self._save_config()
        import shutil
        import sys
        if not shutil.which(self.command[0]):
            print(f"[ERROR] '{self.command[0]}' not found. Is it installed and in your PATH?")
            sys.exit(1)

        self.process = subprocess.Popen(
            self.command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        self.running = True
        self._thread = threading.Thread(target=self._monitor, daemon=True)
        self._thread.start()

    def _monitor(self):
        if not self.process or not self.process.stdout:
            return

        for line in self.process.stdout:
            if not self.running:
                break
            print(line, end="")  # Print to terminal normally

            parsed = parse_log_line(line.rstrip())
            if not parsed:
                continue

            # Buffer a small batch, then process
            with self._buffer_lock:
                self._buffer.append(parsed)
                if len(self._buffer) >= 1:
                    self._process_batch(list(self._buffer))
                    self._buffer.clear()

    def _process_batch(self, logs: list):
        """Process a batch of parsed logs through feature extraction and model."""
        try:
            features, _ = extract_features(logs)
            if features.size == 0:
                self.logs_storage.add_logs(logs)
                return

            self.logs_storage.add_features(features.tolist())
            self.model.predict(features)
            scores = self.model.anomaly_scores(features)

            logs_with_scores = []
            for log, score in zip(logs, scores):
                log_copy = dict(log)
                log_copy["anomaly_score"] = round(float(score), 4)
                logs_with_scores.append(log_copy)

                severity = severity_from_anomaly_score(score, self.model.quantiles, log_level=log.get("level", "INFO"))

                self.alerts_storage.add_alert(
                    service=log.get("service", "app"),
                    severity=severity,
                    log_level=log.get("level", "INFO"),
                    timestamp=log.get("timestamp", ""),
                    anomaly_score=round(float(score), 4),
                    message=log.get("message", ""),
                )
                
                if severity == "Critical":
                    RED = "\033[91m"
                    RESET = "\033[0m"
                    print(f"\n{RED}{'─' * 50}{RESET}")
                    print(f"{RED}🔴 CRITICAL — {log.get('service', 'app')} — {log.get('message', '')}{RESET}")
                    print(f"{RED}   (see dashboard for details){RESET}")
                    print(f"{RED}{'─' * 50}{RESET}\n")

            self.logs_storage.add_logs(logs_with_scores)

        except Exception as e:
            # Fallback — store logs without ML scoring
            for log in logs:
                log["anomaly_score"] = 0.0
            self.logs_storage.add_logs(logs)
            print(f"[WARN] Process wrapper ML scoring failed: {e}")

    def stop(self):
        self.running = False
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
        if self._thread:
            self._thread.join(timeout=1)
