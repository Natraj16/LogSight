const bootSequence = [
    { text: "Loading ML model...", delay: 200 },
    { text: "Loaded legacy model from models/model.pkl", delay: 400 },
    { text: "Starting process wrapper for command: uvicorn app.main:app", delay: 300 },
    { text: "============================================================", delay: 100 },
    { text: "[START] Intelligent Log Analyzer", delay: 100 },
    { text: "============================================================", delay: 100 },
    { text: "INFO:     Uvicorn running on http://127.0.0.1:8000", delay: 600 },
    { text: "12:49:12 │ INFO │ sqlalchemy.engine.Engine │ BEGIN (implicit)", delay: 300 },
    { text: "12:49:12 │ INFO │ caloriq │ ✅ Database tables created", delay: 200, class: "terminal-success" },
    { text: "12:49:12 │ INFO │ caloriq │ 🚀 Caloriq API v0.1.0 is running", delay: 200, class: "terminal-success" },
    { text: "LogSight dashboard running on http://127.0.0.1:5000", delay: 500, class: "terminal-prompt" }
];

document.addEventListener('DOMContentLoaded', async () => {
    const container = document.getElementById('boot-sequence');
    if (!container) return;

    const sleep = (ms) => new Promise(r => setTimeout(r, ms));

    for (let i = 0; i < bootSequence.length; i++) {
        const item = bootSequence[i];
        await sleep(item.delay);
        
        const line = document.createElement('div');
        line.className = 'terminal-line';
        
        const span = document.createElement('span');
        if (item.class) span.className = item.class;
        
        if (i === bootSequence.length - 1) {
            span.innerHTML = `> ${item.text}<span class="boot-cursor" style="display:inline-block; width:8px; height:14px; background:var(--green); animation: blink 1s step-end infinite; margin-left: 4px;"></span>`;
        } else {
            span.textContent = item.text;
        }
        
        line.appendChild(span);
        container.appendChild(line);
    }
});
