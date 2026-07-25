"""Main Flask application and CLI entry point for the log analyzer."""
from __future__ import annotations

import argparse
import json
import os
import sys
import webbrowser
from pathlib import Path
from threading import Timer
from typing import Any

from flask import Flask, render_template, request, jsonify

from .alerts_storage import AlertsStorage
from .log_watcher import LogWatcher
from .logs_storage import LogsStorage
from .model_training import load_or_train_model
from .process_wrapper import ProcessWrapper

# Initialize Flask app
app = Flask(__name__, template_folder="templates")
app.config['TEMPLATES_AUTO_RELOAD'] = True

# Global state
CONFIG_FILE = ".log-analyzer/config.json"
alerts_storage = AlertsStorage()
logs_storage = LogsStorage()
log_watcher: LogWatcher | None = None
process_wrapper: ProcessWrapper | None = None
monitoring = False

# Default config
DEFAULT_CONFIG = {
    "log_path": "logs/application.log",
    "log_levels": ["INFO", "WARN", "ERROR"],
    "custom_levels": "",
    "keywords": "",
}

# Globals
log_watchers = []
model_retrainer = None

# Load ML model
print("Loading ML model...")
model = load_or_train_model()


def load_config() -> dict[str, Any]:
    """Load configuration from file or use defaults."""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return DEFAULT_CONFIG.copy()
    return DEFAULT_CONFIG.copy()


def save_config(config: dict[str, Any]) -> None:
    """Save configuration to file."""
    config_dir = os.path.dirname(CONFIG_FILE)
    if config_dir and not os.path.exists(config_dir):
        os.makedirs(config_dir)
        try:
            with open(os.path.join(config_dir, ".gitignore"), "w") as gf:
                gf.write("*.db\n*.db-journal\n*.db-wal\nconfig.json\n")
        except IOError:
            pass
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)


def launch_dashboard(url="http://127.0.0.1:5000", delay=1.5) -> None:
    """Open the application in the default web browser."""
    Timer(delay, lambda: webbrowser.open(url)).start()


@app.route("/api/config", methods=["GET"])
def get_config() -> dict:
    """Return current configuration."""
    return load_config()


@app.route("/", methods=["GET"])
def index() -> str:
    """Render dashboard page."""
    config = load_config()
    from flask import make_response
    response = make_response(render_template(
        "dashboard.html",
        log_path=config.get("log_path", DEFAULT_CONFIG["log_path"]),
        log_levels=config.get("log_levels", DEFAULT_CONFIG["log_levels"]),
        custom_levels=config.get("custom_levels", ""),
        keywords=config.get("keywords", ""),
    ))
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@app.route("/configure", methods=["POST"])
def configure() -> str:
    """Handle configuration form submission."""
    log_path = request.form.get("log_path", "").strip()
    log_levels = request.form.getlist("log_levels")
    custom_levels = request.form.get("custom_levels", "").strip()
    keywords = request.form.get("keywords", "").strip()

    if not log_levels:
        log_levels = DEFAULT_CONFIG["log_levels"]

    current_config = {
        "log_path": log_path,
        "log_levels": log_levels,
        "custom_levels": custom_levels,
        "keywords": keywords,
    }
    save_config(current_config)

    return render_template(
        "dashboard.html",
        log_path=log_path,
        log_levels=log_levels,
        custom_levels=custom_levels,
        keywords=keywords,
    )


@app.route("/alerts")
def alerts_page() -> str:
    return index()


@app.route("/logs")
def logs_page() -> str:
    return index()


@app.route("/start_monitoring", methods=["POST"])
def start_monitoring() -> dict:
    """Start log monitoring from UI (File watching mode)."""
    global monitoring, log_watchers, demo_generators, model_retrainer

    if monitoring:
        return {"success": False, "message": "Monitoring already running"}

    try:
        config = load_config()
        
        # Clear databases to ensure a clean slate for the new monitoring session
        logs_storage.clear_all()
        alerts_storage.clear_all()
        
        # Resume ProcessWrapper if that was how we started
        if "command" in config:
            global process_wrapper
            process_wrapper = ProcessWrapper(config["command"], model, alerts_storage, logs_storage, config)
            process_wrapper.start()
        else:
            # Fall back to file watching
            log_paths_raw = config.get("log_path", DEFAULT_CONFIG["log_path"])
            log_paths = [p.strip() for p in log_paths_raw.split(",") if p.strip()]
            
            if not log_paths:
                return {"success": False, "message": "No log paths configured"}

            log_watchers = []
            for path in log_paths:
                log_dir = os.path.dirname(path)
                if log_dir and not os.path.exists(log_dir):
                    os.makedirs(log_dir)
                if not os.path.exists(path):
                    from pathlib import Path
                    Path(path).touch()
                    
                watcher = LogWatcher(path, model, alerts_storage, logs_storage, config)
                watcher.start()
                log_watchers.append(watcher)

        from .model import ModelRetrainer
        model_retrainer = ModelRetrainer(model, logs_storage, interval_minutes=5)
        model_retrainer.start()

        monitoring = True
        return {"success": True, "message": "Monitoring started"}

    except Exception as e:
        return {"success": False, "message": str(e)}


@app.route("/stop_monitoring", methods=["POST"])
def stop_monitoring() -> dict:
    """Stop log monitoring."""
    global monitoring, log_watchers, model_retrainer, process_wrapper

    try:
        for watcher in log_watchers:
            watcher.stop()
        log_watchers.clear()

        if model_retrainer:
            model_retrainer.stop()
            model_retrainer = None

        if process_wrapper:
            process_wrapper.stop()
            process_wrapper = None

        monitoring = False
        return {"success": True, "message": "Monitoring stopped"}

    except Exception as e:
        return {"success": False, "message": str(e)}


@app.route("/monitoring_status")
def monitoring_status() -> dict:
    return {"monitoring": monitoring}


@app.route("/api/alerts")
def api_alerts() -> dict:
    alerts = alerts_storage.get_alerts(limit=100)
    counts = alerts_storage.get_alert_count_by_severity()
    return {"alerts": alerts, "alert_counts": counts}


@app.route("/api/clear_alerts", methods=["POST"])
def api_clear_alerts() -> dict:
    alerts_storage.clear_all()
    return {"success": True}





@app.route("/api/logs")
def api_logs() -> dict:
    return {"logs": logs_storage.get_logs(limit=500)}

@app.route("/api/overview_summary")
def api_overview_summary() -> dict:
    """Return all-time summary data for the overview tab pie charts."""
    return {
        "alert_counts": alerts_storage.get_alert_count_by_severity(),
        "log_level_proportions": logs_storage.get_log_level_proportions_all(),
    }

@app.route("/api/analytics")
def api_analytics() -> dict:
    from datetime import datetime, timedelta
    
    range_param = request.args.get("range", "15m")
    now = datetime.now()
    
    if range_param == "15m":
        since_time = now - timedelta(minutes=15)
    elif range_param == "1h":
        since_time = now - timedelta(hours=1)
    elif range_param == "24h":
        since_time = now - timedelta(hours=24)
    else:
        since_time = now - timedelta(minutes=15)
        
    since = since_time.isoformat()
    
    return {
        "severity_over_time": alerts_storage.get_severity_over_time(since),
        "top_noisy_services": alerts_storage.get_top_noisy_services(since),
        "log_level_proportions": logs_storage.get_log_level_proportions(since),
        "anomaly_score_over_time": logs_storage.get_anomaly_score_over_time(since)
    }

def main():
    parser = argparse.ArgumentParser(description="Zero-config ML-based log anomaly detector.")
    subparsers = parser.add_subparsers(dest="command", required=False)

    # Subcommand: run
    run_parser = subparsers.add_parser("run", help="Run and monitor an application process.")
    run_parser.add_argument("process_args", nargs=argparse.REMAINDER, help="Command to run (e.g. 'python app.py')")

    # Subcommand: watch
    watch_parser = subparsers.add_parser("watch", help="Watch one or more existing log files.")
    watch_parser.add_argument("paths", nargs="+", help="Paths to log files to watch.")

    args = parser.parse_args()

    global monitoring, process_wrapper, log_watchers, model_retrainer

    if args.command == "run":
        if not args.process_args:
            # Handle "--" correctly if argparse didn't group it
            pass 
        cmd = args.process_args
        if cmd and cmd[0] == "--":
            cmd = cmd[1:]
        
        if not cmd:
            print("Error: Must provide a command to run (e.g., 'log-analyzer run -- python app.py')")
            sys.exit(1)

        print(f"Starting process wrapper for command: {' '.join(cmd)}")
        config = load_config()
        
        # Clear databases on fresh CLI start
        logs_storage.clear_all()
        alerts_storage.clear_all()
        
        process_wrapper = ProcessWrapper(cmd, model, alerts_storage, logs_storage, config)
        process_wrapper.start()
        monitoring = True

        from .model import ModelRetrainer
        model_retrainer = ModelRetrainer(model, logs_storage, interval_minutes=5)
        model_retrainer.start()

    elif args.command == "watch":
        log_paths = args.paths
        config = load_config()
        
        # Clear databases on fresh CLI start
        logs_storage.clear_all()
        alerts_storage.clear_all()
        
        for path in log_paths:
            if not os.path.exists(path):
                print(f"File {path} does not exist, creating it.")
                Path(path).touch()
            
            watcher = LogWatcher(path, model, alerts_storage, logs_storage, config)
            watcher.start()
            log_watchers.append(watcher)
            print(f"Watching file: {path}")

        from .model import ModelRetrainer
        model_retrainer = ModelRetrainer(model, logs_storage, interval_minutes=5)
        model_retrainer.start()
        monitoring = True

    print("=" * 60)
    print("[START] Intelligent Log Analyzer")
    print("============================================================")
    
    import socket
    import signal

    def find_free_port(start=5000, max_tries=20):
        for port in range(start, start + max_tries):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                if s.connect_ex(("127.0.0.1", port)) != 0:
                    return port
        raise RuntimeError("No free port found")
        
    try:
        free_port = find_free_port()
    except RuntimeError:
        free_port = 5000

    def handle_shutdown(signum, frame):
        if process_wrapper:
            process_wrapper.stop()
        for watcher in log_watchers:
            watcher.stop()
        if model_retrainer:
            model_retrainer.stop()
        print("Shutting down...")
        sys.exit(0)

    try:
        signal.signal(signal.SIGINT, handle_shutdown)
        signal.signal(signal.SIGTERM, handle_shutdown)
    except ValueError:
        pass

    launch_dashboard(url=f"http://127.0.0.1:{free_port}")
    
    # First-run disclosure (11.1)
    print("\n[Notice] LogSight captures stdout/stderr from your wrapped process and stores it locally in `.log-analyzer/`.")
    print("         It does not leave your machine. Known secret patterns are redacted automatically,")
    print("         but review sensitive output before sharing your logs.\n")
    
    # Silence the noisy Werkzeug access logs
    import logging
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    
    try:
        app.run(host="0.0.0.0", port=free_port, debug=False, use_reloader=False)
    except Exception:
        pass
    finally:
        handle_shutdown(None, None)

if __name__ == "__main__":
    main()
