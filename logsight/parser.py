from __future__ import annotations

import re
import json
from datetime import datetime
from typing import Dict, List, Optional

FORMAT_PATTERNS = [
    # Python logging: 2026-07-23 14:17:47,123 - auth-service - INFO - message
    ("python_logging", re.compile(
        r'^(?P<ts>\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?)\s+-\s+'
        r'(?P<service>\S+)\s+-\s+'
        r'(?P<level>DEBUG|INFO|WARN(?:ING)?|ERROR|CRITICAL|FATAL)\s+-\s+'
        r'(?P<rest>.*)$', re.IGNORECASE)),

    ("iso_standard", re.compile(
        r'^(?P<ts>\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?)\s+'
        r'(?P<level>DEBUG|INFO|WARN(?:ING)?|ERROR|CRITICAL|FATAL)\s+'
        r'(?P<service>\S+)\s+'
        r'(?P<rest>.*)$', re.IGNORECASE)),

    ("iso_standard_no_service", re.compile(
        r'^(?P<ts>\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?)\s+'
        r'(?P<level>DEBUG|INFO|WARN(?:ING)?|ERROR|CRITICAL|FATAL)\s+'
        r'(?P<rest>.*)$', re.IGNORECASE)),

    ("rich_textual", re.compile(
        r'^(?P<ts>\d{2}:\d{2}:\d{2}(?:\.\d+)?)\s*(?:│|\||\\u2502)\s*(?P<level>[A-Za-z]+)\s*(?:│|\||\\u2502)\s*(?P<service>[^│|]+?)\s*(?:│|\||\\u2502)\s*(?P<rest>.*)$', re.IGNORECASE)),

    ("uvicorn_style", re.compile(
        r'^(?P<level>INFO|WARNING|ERROR|DEBUG|CRITICAL):\s+(?P<rest>.*)$', re.IGNORECASE)),

    ("bracketed_level", re.compile(
        r'^\[?(?P<ts>\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}[^\]]*)\]?\s*'
        r'\[?(?P<level>DEBUG|INFO|WARN(?:ING)?|ERROR|CRITICAL)\]?\s*'
        r'(?P<rest>.*)$', re.IGNORECASE)),

    ("syslog_style", re.compile(
        r'^(?P<ts>\w{3}\s+\d+\s+\d{2}:\d{2}:\d{2})\s+(?P<host>\S+)\s+(?P<rest>.*)$')),
]

SECRET_PATTERNS = [
    (re.compile(r'(api[_-]?key["\s:=]+)([A-Za-z0-9\-_]{16,})', re.IGNORECASE), r'\1[REDACTED]'),
    (re.compile(r'(password["\s:=]+)(\S+)', re.IGNORECASE), r'\1[REDACTED]'),
    (re.compile(r'(bearer\s+)([A-Za-z0-9\-_\.]{20,})', re.IGNORECASE), r'\1[REDACTED]'),
    (re.compile(r'AKIA[0-9A-Z]{16}'), '[REDACTED_AWS_KEY]'),
    (re.compile(r'eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}'), '[REDACTED_JWT]'),
]

def redact(message: str) -> str:
    for pattern, replacement in SECRET_PATTERNS:
        message = pattern.sub(replacement, message)
    return message

def parse_log_line(line: str, default_service: str = "unknown") -> Optional[Dict[str, str]]:
    """Parse one log line into a structured dictionary."""
    raw_line = line.strip()
    if not raw_line:
        return None
        
    raw_line = redact(raw_line)

    if raw_line.startswith("{"):
        try:
            data = json.loads(raw_line)
            return {
                "raw_line": raw_line,
                "timestamp": data.get("timestamp") or data.get("time") or datetime.now().isoformat(sep=" "),
                "level": str(data.get("level") or data.get("severity") or "INFO").upper().replace("WARNING", "WARN"),
                "service": data.get("service") or data.get("logger") or default_service,
                "message": data.get("message") or data.get("msg") or raw_line,
                "parse_method": "json",
            }
        except json.JSONDecodeError:
            pass

    for name, pattern in FORMAT_PATTERNS:
        match = pattern.match(raw_line)
        if match:
            groups = match.groupdict()
            service = groups.get("service")
            if not service and name == "uvicorn_style":
                service = "uvicorn"
            return {
                "raw_line": raw_line,
                "timestamp": groups.get("ts") or datetime.now().isoformat(sep=" "),
                "level": groups.get("level", "INFO").upper().replace("WARNING", "WARN"),
                "service": (service.strip() if service else default_service),
                "message": groups.get("rest", raw_line).strip(),
                "parse_method": name,
            }

    lowered = raw_line.lower()
    if any(k in lowered for k in ("error", "exception", "traceback", "failed", "fatal")):
        level = "ERROR"
    elif any(k in lowered for k in ("warn", "deprecat", "retry")):
        level = "WARN"
    else:
        level = "INFO"

    # Attempt to extract a [Tag] or Service: from the beginning of the line as a fallback
    service = default_service
    message = raw_line
    
    tag_match = re.match(r'^\[([A-Za-z0-9_.-]+)\]\s*(.*)', raw_line)
    if tag_match:
        service = tag_match.group(1)
        message = tag_match.group(2)
    else:
        colon_match = re.match(r'^([A-Za-z0-9_.-]+):\s+(.*)', raw_line)
        if colon_match:
            pot_svc = colon_match.group(1)
            if pot_svc.upper() not in {"INFO", "WARNING", "WARN", "ERROR", "DEBUG", "CRITICAL", "FATAL"}:
                service = pot_svc
                message = colon_match.group(2)
        elif re.match(r'^\s*(SELECT|FROM|WHERE|AND|OR|INSERT|UPDATE|DELETE|JOIN|LEFT JOIN|GROUP BY|ORDER BY|LIMIT)\b', raw_line, re.IGNORECASE):
            service = "sqlalchemy.query"
            message = raw_line

    return {
        "raw_line": raw_line,
        "timestamp": datetime.now().isoformat(sep=" "),
        "level": level,
        "service": service,
        "message": message,
        "parse_method": "heuristic_fallback",
    }

def parse_log_file(file_path: str) -> List[Dict[str, str]]:
    """Read and parse all valid log lines from a file."""
    parsed_logs: List[Dict[str, str]] = []

    try:
        with open(file_path, "r", encoding="utf-8") as log_file:
            for line in log_file:
                parsed = parse_log_line(line)
                if parsed:
                    parsed_logs.append(parsed)
    except FileNotFoundError:
        pass

    return parsed_logs
