# LogSight

**LogSight** is a zero-config, local, ML-based real-time log anomaly detector designed for solo developers, indie hackers, and students.

## The Origin Story
This project started as a final year college project with a simple premise: **"What if we could apply Machine Learning to local logs without setting up a massive ELK stack?"** 

Traditionally, log analytics (DataDog, Splunk, ELK) requires complex infrastructure, log shippers, hosted databases, and significant configuration. For a solo developer or student hacking together a small project, setting up ELK is massive overkill.

**LogSight** was born to bridge this gap. It evolved from a basic text-parsing script into a fully-fledged CLI tool with a premium, futuristic browser dashboard, all running locally. We built an unsupervised Machine Learning pipeline using an Isolation Forest to score logs in real-time, extracting features like log levels, text characteristics, and rate of generation. It now features secret redaction, auto-retraining for local sessions, and terminal inline alerts—bringing enterprise-grade analytics to your local `localhost` development environment.

## Features
- **Zero Configuration**: No servers to set up, no databases to provision. Just wrap your existing command.
- **Real-Time ML Anomaly Detection**: Uses `scikit-learn` Isolation Forests to detect unusual log patterns.
- **Beautiful Local Dashboard**: A premium, futuristic UI with dark-mode glassmorphism and real-time Chart.js graphs.
- **Secret Scrubbing**: Automatically detects and redacts API keys, AWS credentials, JWTs, and passwords.
- **Multi-channel Alerts**: Browser tab badging, terminal inline alerts, and toggleable sound cues.
- **Smart Retraining**: Adapts automatically to your local application's baseline log behavior.

## Installation

LogSight is designed to be installed globally via `pip`.

```bash
pip install logsight
```

### Developing from source
If you want to contribute or modify LogSight locally:
```bash
git clone https://github.com/Natraj16/LogSight.git
cd LogSight
pip install -e .
```

## Usage

LogSight has two main modes: `run` and `watch`.

### 1. Run Mode (Wrapper)
Wrap any existing command that outputs logs to stdout/stderr. Because LogSight acts purely as a wrapper around the standard output, **you can run it on any application without making any code changes or configuration updates**. LogSight will intercept the output, parse it, run ML scoring, and serve the dashboard—all while passing the original output to your terminal.

```bash
# Wrap a Python app
logsight run -- python app.py

# Wrap a React/Next.js/Node app
logsight run -- npm run dev

# Wrap a Docker Compose stack
logsight run -- docker-compose up
```

### 2. Watch Mode
If your application already writes logs to a file, LogSight can simply tail that file.

```bash
logsight watch path/to/application.log
```

## The Dashboard
Once started, LogSight automatically opens a beautiful dashboard in your browser (default `http://127.0.0.1:5000`).
The dashboard provides:
- Live streaming log tailing.
- Severity distribution and anomaly scoring over time.
- Top noisy services.
- Critical alert feed with audio and visual cues.

## Tech Stack
- **Backend**: Python, Flask, subprocess, threading.
- **Machine Learning**: `scikit-learn` (IsolationForest), `numpy`.
- **Frontend**: HTML5, Vanilla CSS, JS, Chart.js.

## Contributing
Since this started as a student project, contributions, ideas, and pull requests are highly encouraged! Feel free to open an issue to discuss new features or bug fixes.
