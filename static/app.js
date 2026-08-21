let simRunning = true;
let telemetryChart = null;
const serverColors = {
    "srv-prod-east-01": "#38bdf8",     // Light blue
    "srv-prod-east-02": "#6366f1",     // Indigo
    "srv-prod-west-01": "#f43f5e",     // GCP Red
    "srv-prod-west-02": "#ec4899",     // Pink
    "srv-deloitte-prod-01": "#10b981"  // Deloitte Green
};

// Initialize on page load
document.addEventListener("DOMContentLoaded", () => {
    initChart();
    fetchStats();
    fetchTelemetry();
    fetchLogs();
    fetchAlerts();
    checkSimulatorStatus();

    // Setup polling every 1 second
    setInterval(() => {
        if (simRunning) {
            fetchStats();
            fetchTelemetry();
            fetchAlerts();
            if (!document.getElementById('filter-search').value) {
                fetchLogs();
            }
        }
    }, 1000);
});

function initChart() {
    const ctx = document.getElementById('telemetryChart').getContext('2d');
    telemetryChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [], // Timestamps
            datasets: [] // One dataset per server
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                mode: 'index',
                intersect: false
            },
            scales: {
                x: {
                    grid: { color: 'rgba(255, 255, 255, 0.03)' },
                    ticks: { color: '#64748b', font: { family: 'Outfit', size: 9 } }
                },
                y: {
                    min: 0,
                    max: 100,
                    grid: { color: 'rgba(255, 255, 255, 0.05)' },
                    ticks: { color: '#64748b', font: { family: 'Outfit', size: 9 } }
                }
            },
            plugins: {
                legend: {
                    position: 'top',
                    labels: { 
                        color: '#cbd5e1', 
                        font: { family: 'Outfit', size: 10, weight: 'bold' },
                        boxWidth: 10,
                        padding: 10
                    }
                },
                tooltip: {
                    backgroundColor: 'rgba(15, 23, 42, 0.95)',
                    titleColor: '#38bdf8',
                    bodyColor: '#f8fafc',
                    borderColor: 'rgba(255, 255, 255, 0.1)',
                    borderWidth: 1,
                    titleFont: { family: 'Outfit', size: 11, weight: 'bold' },
                    bodyFont: { family: 'Outfit', size: 10 },
                    padding: 8,
                    displayColors: true,
                    boxWidth: 8,
                    boxHeight: 8
                }
            },
            elements: {
                point: { radius: 0, hoverRadius: 5 },
                line: { tension: 0.4, borderWidth: 3 }
            }
        }
    });
}

async function checkSimulatorStatus() {
    try {
        const response = await fetch('/api/status');
        const data = await response.json();
        simRunning = data.running;
        updateSimBtnUI();
    } catch (e) {
        console.error("Error checking simulator status:", e);
    }
}

async function toggleSimulator() {
    const action = simRunning ? 'stop' : 'start';
    try {
        const response = await fetch(`/api/status/toggle?action=${action}`, { method: 'POST' });
        const data = await response.json();
        simRunning = data.running;
        updateSimBtnUI();
    } catch (e) {
        console.error("Error toggling simulator:", e);
    }
}

function updateSimBtnUI() {
    const btn = document.getElementById('toggle-sim-btn');
    const badge = document.getElementById('system-status-badge');
    const pulse = document.getElementById('system-pulse');
    const text = document.getElementById('system-status-text');

    if (simRunning) {
        btn.innerText = "Pause Simulator";
        btn.style.borderColor = "var(--card-border)";
        badge.style.background = "rgba(16, 185, 129, 0.15)";
        badge.style.borderColor = "rgba(16, 185, 129, 0.3)";
        pulse.style.backgroundColor = "var(--color-success)";
        text.innerText = "Pipeline Operational";
    } else {
        btn.innerText = "Resume Simulator";
        btn.style.borderColor = "rgba(245, 158, 11, 0.5)";
        badge.style.background = "rgba(245, 158, 11, 0.15)";
        badge.style.borderColor = "rgba(245, 158, 11, 0.3)";
        pulse.style.backgroundColor = "var(--color-warning)";
        text.innerText = "Pipeline Paused";
    }
}

async function fetchStats() {
    try {
        const response = await fetch('/api/stats');
        const data = await response.json();
        
        document.getElementById('stat-rate').innerText = `${data.ingestion_rate_processed}`;
        document.getElementById('stat-total').innerText = data.total_logs;
        document.getElementById('stat-alerts').innerText = data.active_alerts;
        document.getElementById('stat-critical').innerText = data.critical_errors;
        
        const alertStat = document.getElementById('stat-alerts');
        if (data.active_alerts > 0) {
            alertStat.style.color = 'var(--color-critical)';
        } else {
            alertStat.style.color = 'var(--color-warning)';
        }
    } catch (e) {
        console.error("Error fetching stats:", e);
    }
}

async function fetchTelemetry() {
    try {
        const response = await fetch('/api/telemetry');
        const telemetry = await response.json();
        
        const container = document.getElementById('server-metrics-container');
        container.innerHTML = '';
        
        let timestamps = [];
        let chartDatasets = [];
        
        const sortedServers = Object.keys(telemetry).sort();
        for (const server of sortedServers) {
            const history = telemetry[server];
            if (history.length === 0) continue;
            
            const latest = history[history.length - 1];
            const cpu = latest.cpu_utilization.toFixed(1);
            const mem = latest.memory_utilization.toFixed(1);
            const disk = latest.disk_utilization.toFixed(1);
            const provider = server.includes('west') ? 'GCP' : 'Azure';
            
            const cpuColor = cpu > 90 ? 'var(--color-critical)' : (cpu > 75 ? 'var(--color-warning)' : 'var(--color-success)');
            const memColor = mem > 85 ? 'var(--color-critical)' : (mem > 70 ? 'var(--color-warning)' : 'var(--color-success)');
            const diskColor = disk > 90 ? 'var(--color-critical)' : (disk > 80 ? 'var(--color-warning)' : 'var(--color-success)');
            
            const cardHtml = `
                <div class="server-card">
                    <div class="server-header">
                        <span class="server-name">${server}</span>
                        <span class="log-provider ${provider}" style="font-size: 0.8rem;">${provider}</span>
                    </div>
                    
                    <div class="metric-row">
                        <div class="metric-header">
                            <span>CPU Utilization</span>
                            <span style="color: ${cpuColor}">${cpu}%</span>
                        </div>
                        <div class="progress-bar-container">
                            <div class="progress-bar" style="width: ${cpu}%; background-color: ${cpuColor}"></div>
                        </div>
                    </div>
                    
                    <div class="metric-row">
                        <div class="metric-header">
                            <span>Memory Utilization</span>
                            <span style="color: ${memColor}">${mem}%</span>
                        </div>
                        <div class="progress-bar-container">
                            <div class="progress-bar" style="width: ${mem}%; background-color: ${memColor}"></div>
                        </div>
                    </div>

                    <div class="metric-row">
                        <div class="metric-header">
                            <span>Disk Utilization</span>
                            <span style="color: ${diskColor}">${disk}%</span>
                        </div>
                        <div class="progress-bar-container">
                            <div class="progress-bar" style="width: ${disk}%; background-color: ${diskColor}"></div>
                        </div>
                    </div>
                </div>
            `;
            container.insertAdjacentHTML('beforeend', cardHtml);
            
            // Collect Chart Data
            if (timestamps.length === 0) {
                timestamps = history.map(h => new Date(h.timestamp).toLocaleTimeString());
            }
            
            const cpuHistory = history.map(h => h.cpu_utilization);
            let datasetColor = serverColors[server];
            if (!datasetColor) {
                // If it is a local host, color it high-visibility neon cyan/blue
                datasetColor = "#a855f7"; // Neon Purple for Host
            }
            
            chartDatasets.push({
                label: server,
                data: cpuHistory,
                borderColor: datasetColor,
                backgroundColor: 'transparent',
                borderWidth: 3,
                pointHoverRadius: 5
            });
        }
        
        // Update Chart
        if (telemetryChart) {
            telemetryChart.data.labels = timestamps;
            telemetryChart.data.datasets = chartDatasets;
            telemetryChart.update();
        }
        
    } catch (e) {
        console.error("Error fetching telemetry:", e);
    }
}

async function fetchLogs() {
    const level = document.getElementById('filter-level').value;
    const provider = document.getElementById('filter-provider').value;
    const search = document.getElementById('filter-search').value;
    
    let url = `/api/logs?limit=50`;
    if (level !== 'ALL') url += `&level=${level}`;
    if (provider !== 'ALL') url += `&provider=${provider}`;
    if (search) url += `&search=${encodeURIComponent(search)}`;
    
    try {
        const response = await fetch(url);
        const logs = await response.json();
        
        const container = document.getElementById('log-stream-container');
        container.innerHTML = '';
        
        if (logs.length === 0) {
            container.innerHTML = `<div style="color: var(--color-muted); text-align: center; padding-top: 1rem;">No matching logs found.</div>`;
            return;
        }
        
        logs.forEach(log => {
            const timeFormatted = new Date(log.timestamp).toLocaleTimeString();
            const logLine = `
                <div class="log-line">
                    <span class="log-time">[${timeFormatted}]</span>
                    <span class="log-level ${log.level}">${log.level}</span>
                    <span class="log-provider ${log.cloud_provider}">${log.cloud_provider}</span>
                    <span style="color: var(--color-muted); font-weight:600;">${log.server_id}:</span>
                    <span class="log-msg">${log.message}</span>
                </div>
            `;
            container.insertAdjacentHTML('beforeend', logLine);
        });
    } catch (e) {
        console.error("Error fetching logs:", e);
    }
}

function searchLogs(event) {
    if (event.key === "Enter") {
        fetchLogs();
    }
}

async function fetchAlerts() {
    try {
        const response = await fetch('/api/alerts');
        const alerts = await response.json();
        
        const container = document.getElementById('alert-list-container');
        container.innerHTML = '';
        
        const activeAlerts = alerts.filter(a => a.resolved === 0);
        
        if (activeAlerts.length === 0) {
            container.innerHTML = `<div style="text-align: center; color: var(--color-muted); padding-top: 2rem;">No active alerts. System healthy.</div>`;
            return;
        }
        
        activeAlerts.forEach(alert => {
            const time = new Date(alert.timestamp).toLocaleTimeString();
            const alertHtml = `
                <div class="alert-item">
                    <div class="alert-header">
                        <span style="color: var(--color-critical);">${alert.severity}</span>
                        <span style="color: var(--color-muted);">${time}</span>
                    </div>
                    <div class="alert-desc">
                        <strong>${alert.server_id}</strong> is experiencing high <strong>${alert.metric}</strong>: ${alert.value.toFixed(1)}%
                    </div>
                </div>
            `;
            container.insertAdjacentHTML('beforeend', alertHtml);
        });
    } catch (e) {
        console.error("Error fetching alerts:", e);
    }
}

async function injectIncident() {
    const server = document.getElementById('inject-server').value;
    const metric = document.getElementById('inject-metric').value;
    
    try {
        const response = await fetch(`/api/inject?server=${server}&metric=${metric}`, { method: 'POST' });
        const res = await response.json();
        if (res.status === 'incident_injected') {
            fetchStats();
            fetchAlerts();
            fetchLogs();
            alert(`Successfully injected incident: ${metric} spike on ${server}. Check Alert Inbox & Mini-Splunk!`);
        }
    } catch (e) {
        console.error("Error injecting incident:", e);
    }
}
