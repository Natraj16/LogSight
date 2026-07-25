"""SQLite-backed log storage and management."""
from __future__ import annotations

import sqlite3
import threading
from typing import Dict, List
import os


class LogsStorage:
    def __init__(self, max_logs: int = 500, db_path: str = "data/logsight.db"):
        self.max_logs = max_logs
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self.lock = threading.RLock()
        
        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute('''
                    CREATE TABLE IF NOT EXISTS logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT,
                        level TEXT,
                        service TEXT,
                        message TEXT,
                        anomaly_score REAL
                    )
                ''')
                conn.execute('''
                    CREATE TABLE IF NOT EXISTS feature_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT,
                        f1 REAL,
                        f2 REAL,
                        f3 REAL,
                        f4 REAL
                    )
                ''')

    def add_logs(self, entries: List[Dict]) -> None:
        """Add parsed log entries to storage."""
        if not entries:
            return
        with self.lock:
            with sqlite3.connect(self.db_path, timeout=10) as conn:
                for log in entries:
                    conn.execute('''
                        INSERT INTO logs (timestamp, level, service, message, anomaly_score)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (log.get("timestamp"), log.get("level"), log.get("service"), log.get("message"), log.get("anomaly_score", 0.0)))
                
                count = conn.execute("SELECT COUNT(*) FROM logs").fetchone()[0]
                if count > self.max_logs:
                    conn.execute(f"DELETE FROM logs WHERE id NOT IN (SELECT id FROM logs ORDER BY id DESC LIMIT {self.max_logs})")

    def add_features(self, features: List[List[float]], max_features: int = 5000) -> None:
        """Add extracted feature vectors to history for retraining."""
        if not features:
            return
        from datetime import datetime
        with self.lock:
            with sqlite3.connect(self.db_path, timeout=10) as conn:
                timestamp = datetime.now().isoformat(sep=" ")
                for f in features:
                    conn.execute('''
                        INSERT INTO feature_history (timestamp, f1, f2, f3, f4)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (timestamp, f[0], f[1], f[2], f[3]))
                
                count = conn.execute("SELECT COUNT(*) FROM feature_history").fetchone()[0]
                if count > max_features:
                    conn.execute(f"DELETE FROM feature_history WHERE id NOT IN (SELECT id FROM feature_history ORDER BY id DESC LIMIT {max_features})")

    def get_recent_features(self, limit: int = 5000) -> List[List[float]]:
        """Get recent feature vectors for model retraining."""
        with self.lock:
            with sqlite3.connect(self.db_path, timeout=10) as conn:
                cursor = conn.execute(
                    "SELECT f1, f2, f3, f4 FROM feature_history ORDER BY id DESC LIMIT ?",
                    (limit,)
                )
                rows = cursor.fetchall()
                # Return oldest first for temporal consistency
                rows.reverse()
                return [[r[0], r[1], r[2], r[3]] for r in rows]

    def _row_to_dict(self, row) -> Dict:
        return {
            "id": row[0],
            "timestamp": row[1],
            "level": row[2],
            "service": row[3],
            "message": row[4],
            "anomaly_score": round(row[5], 4) if row[5] is not None else 0.0,
        }

    def get_logs(self, limit: int = 500) -> List[Dict]:
        """Get stored logs (oldest to newest)."""
        with self.lock:
            if limit <= 0:
                return []
            with sqlite3.connect(self.db_path, timeout=10) as conn:
                # We want oldest to newest for the limit requested, which means ORDER BY id DESC, limit, and then reverse
                cursor = conn.execute(
                    "SELECT id, timestamp, level, service, message, anomaly_score FROM logs ORDER BY id DESC LIMIT ?",
                    (limit,)
                )
                rows = cursor.fetchall()
                # Reverse to make it oldest to newest
                rows.reverse()
                return [self._row_to_dict(row) for row in rows]

    def clear_all(self) -> None:
        """Clear all stored logs."""
        with self.lock:
            with sqlite3.connect(self.db_path, timeout=10) as conn:
                conn.execute("DELETE FROM logs")

    def get_log_level_proportions(self, since: str) -> Dict[str, int]:
        """Get counts of logs grouped by level since a timestamp."""
        # Normalize: logs store timestamps with space (from parser), since uses T
        since_normalized = since.replace("T", " ")
        with self.lock:
            with sqlite3.connect(self.db_path, timeout=10) as conn:
                cursor = conn.execute(
                    "SELECT level, COUNT(*) FROM logs WHERE REPLACE(timestamp, 'T', ' ') >= ? GROUP BY level",
                    (since_normalized,)
                )
                return {row[0]: row[1] for row in cursor.fetchall()}

    def get_log_level_proportions_all(self) -> Dict[str, int]:
        """Get counts of all logs grouped by level (no time filter)."""
        with self.lock:
            with sqlite3.connect(self.db_path, timeout=10) as conn:
                cursor = conn.execute(
                    "SELECT level, COUNT(*) FROM logs GROUP BY level"
                )
                return {row[0]: row[1] for row in cursor.fetchall()}

    def get_anomaly_score_over_time(self, since: str) -> List[Dict]:
        """Get max anomaly score per minute since a timestamp."""
        since_normalized = since.replace("T", " ")
        with self.lock:
            with sqlite3.connect(self.db_path, timeout=10) as conn:
                cursor = conn.execute('''
                    SELECT substr(REPLACE(timestamp, 'T', ' '), 1, 16) as minute_bucket, 
                           MAX(anomaly_score) as score
                    FROM logs
                    WHERE REPLACE(timestamp, 'T', ' ') >= ?
                    GROUP BY minute_bucket
                    ORDER BY minute_bucket ASC
                ''', (since_normalized,))
                return [{"timestamp": row[0], "score": row[1]} for row in cursor.fetchall()]


