import pytest
from logsight.parser import parse_log_line, redact

def test_secret_redaction():
    # Test API key redaction
    log = '2026-07-23 14:17:47 INFO api_key="sk-live-1234567890abcdef1234567890abcdef" starting'
    parsed = parse_log_line(log)
    assert 'sk-live-' not in parsed['raw_line']
    assert '[REDACTED]' in parsed['raw_line']

    # Test AWS Key redaction
    log = 'DEBUG found credentials AKIAIOSFODNN7EXAMPLE in config'
    parsed = parse_log_line(log)
    assert 'AKIAIOSFODNN7EXAMPLE' not in parsed['raw_line']
    assert '[REDACTED_AWS_KEY]' in parsed['raw_line']

    # Test JWT redaction
    log = 'WARN Token eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c expired'
    parsed = parse_log_line(log)
    assert 'eyJhbGci' not in parsed['raw_line']
    assert '[REDACTED_JWT]' in parsed['raw_line']

def test_parse_json():
    log = '{"time": "2026-07-23 14:17:47", "level": "ERROR", "service": "db", "message": "Connection lost"}'
    parsed = parse_log_line(log)
    assert parsed["level"] == "ERROR"
    assert parsed["service"] == "db"
    assert parsed["message"] == "Connection lost"
    assert parsed["parse_method"] == "json"

def test_parse_python_logging():
    log = '2026-07-23 14:17:47,123 - auth-service - INFO - user logged in'
    parsed = parse_log_line(log)
    assert parsed["level"] == "INFO"
    assert parsed["service"] == "auth-service"
    assert parsed["message"] == "user logged in"
    assert parsed["parse_method"] == "python_logging"

def test_parse_uvicorn():
    log = 'INFO:     Application startup complete.'
    parsed = parse_log_line(log)
    assert parsed["level"] == "INFO"
    assert parsed["message"] == "Application startup complete."
    assert parsed["parse_method"] == "uvicorn_style"

def test_heuristic_fallback():
    log = 'Exception in thread "main" java.lang.NullPointerException'
    parsed = parse_log_line(log)
    assert parsed["level"] == "ERROR"
    assert parsed["parse_method"] == "heuristic_fallback"
