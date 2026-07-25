"""SQLite-backed alert storage and management."""
from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import os


class AlertsStorage:
    def __init__(self, max_alerts: int = 5000, db_path: str = "data/logsight.db"):
        self.max_alerts = max_alerts
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self.lock = threading.RLock()
        
        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute('''
                    CREATE TABLE IF NOT EXISTS alerts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT,
                        log_timestamp TEXT,
                        service TEXT,
                        message TEXT,
                        severity TEXT,
                        log_level TEXT,
                        anomaly_score REAL
                    );
                ''')

    def add_alert(
        self,
        service: str,
        severity: str,
        log_level: str,
        timestamp: str,
        anomaly_score: float = 0.0,
        message: str = "",
    ) -> None:
        """Add a new alert to storage."""
        if isinstance(service, dict):
            # Compatibility with process_wrapper calling add_alert with a dict
            alert_dict = service
            service = alert_dict.get("service", "app")
            severity = alert_dict.get("severity", "High")
            log_level = alert_dict.get("level", "ERROR")
            timestamp = alert_dict.get("timestamp", datetime.now().isoformat())
            anomaly_score = alert_dict.get("score", 0.0)
            message = alert_dict.get("message", "")

        with self.lock:
            with sqlite3.connect(self.db_path, timeout=10) as conn:
                conn.execute('''
                    INSERT INTO alerts (timestamp, log_timestamp, service, message, severity, log_level, anomaly_score)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (datetime.now().isoformat(), timestamp, service, message, severity, log_level, anomaly_score))
                
                # Trim old alerts if necessary
                count = conn.execute("SELECT COUNT(*) FROM alerts").fetchone()[0]
                if count > self.max_alerts:
                    conn.execute(f"DELETE FROM alerts WHERE id NOT IN (SELECT id FROM alerts ORDER BY id DESC LIMIT {self.max_alerts})")

    def _row_to_dict(self, row) -> Dict:
        return {
            "id": row[0],
            "timestamp": row[1],
            "log_timestamp": row[2],
            "service": row[3],
            "message": row[4],
            "severity": row[5],
            "log_level": row[6],
            "anomaly_score": round(row[7], 4) if row[7] is not None else 0.0,
        }



    def get_alerts(
        self,
        severity: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict]:
        """Get alerts, optionally filtered by severity. Most recent first."""
        with self.lock:
            with sqlite3.connect(self.db_path, timeout=10) as conn:
                if severity:
                    cursor = conn.execute(
                        "SELECT id, timestamp, log_timestamp, service, message, severity, log_level, anomaly_score FROM alerts WHERE severity = ? ORDER BY id DESC LIMIT ?",
                        (severity, limit)
                    )
                else:
                    cursor = conn.execute(
                        "SELECT id, timestamp, log_timestamp, service, message, severity, log_level, anomaly_score FROM alerts ORDER BY id DESC LIMIT ?",
                        (limit,)
                    )
                return [self._row_to_dict(row) for row in cursor.fetchall()]

    def get_alert_count_by_severity(self, since: Optional[str] = None) -> Dict[str, int]:
        """Get count of alerts grouped by severity."""
        with self.lock:
            with sqlite3.connect(self.db_path, timeout=10) as conn:
                if since:
                    cursor = conn.execute("SELECT severity, COUNT(*) FROM alerts WHERE timestamp >= ? GROUP BY severity", (since,))
                else:
                    cursor = conn.execute("SELECT severity, COUNT(*) FROM alerts GROUP BY severity")
                return {row[0]: row[1] for row in cursor.fetchall()}

    def clear_all(self) -> None:
        """Clear all alerts."""
        with self.lock:
            with sqlite3.connect(self.db_path, timeout=10) as conn:
                conn.execute("DELETE FROM alerts")

    def get_total_count(self) -> int:
        """Get total number of alerts."""
        with self.lock:
            with sqlite3.connect(self.db_path, timeout=10) as conn:
                return conn.execute("SELECT COUNT(*) FROM alerts").fetchone()[0]

    def get_top_noisy_services(self, since: str, limit: int = 5) -> List[Dict]:
        with self.lock:
            with sqlite3.connect(self.db_path, timeout=10) as conn:
                cursor = conn.execute('''
                    SELECT service, COUNT(*) as count 
                    FROM alerts 
                    WHERE timestamp >= ? 
                    GROUP BY service 
                    ORDER BY count DESC 
                    LIMIT ?
                ''', (since, limit))
                return [{"service": row[0], "count": row[1]} for row in cursor.fetchall()]

    def get_severity_over_time(self, since: str) -> List[Dict]:
        with self.lock:
            with sqlite3.connect(self.db_path, timeout=10) as conn:
                # Group by hour and minute to create a time series (YYYY-MM-DD HH:MM)
                cursor = conn.execute('''
                    SELECT substr(timestamp, 1, 16) as minute_bucket, severity, COUNT(*) as count
                    FROM alerts
                    WHERE timestamp >= ?
                    GROUP BY minute_bucket, severity
                    ORDER BY minute_bucket ASC
                ''', (since,))
                
                buckets = {}
                for row in cursor.fetchall():
                    bucket, severity, count = row[0], row[1], row[2]
                    if bucket not in buckets:
                        buckets[bucket] = {"Critical": 0, "High": 0, "Medium": 0, "Low": 0}
                    if severity in buckets[bucket]:
                        buckets[bucket][severity] = count
                
                result = []
                for bucket, counts in buckets.items():
                    result.append({
                        "timestamp": bucket + ":00",
                        **counts
                    })
                return result
