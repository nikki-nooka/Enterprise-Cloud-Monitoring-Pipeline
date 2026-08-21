from fastapi import FastAPI, Query, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import sqlite3
import pipeline_simulator
import os
import requests
from datetime import datetime

app = FastAPI(title="Enterprise Monitoring Pipeline API")

# Optional Slack Webhook configuration
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL", "")

class AgentTelemetry(BaseModel):
    server_id: str
    cpu_utilization: float
    memory_utilization: float
    disk_utilization: float
    throughput_kbps: float

class AgentLog(BaseModel):
    cloud_provider: str
    service: str
    level: str
    message: str
    server_id: str
    status_code: int

# Ensure database is initialized and simulator is running
@app.on_event("startup")
def startup_event():
    pipeline_simulator.start_simulator()

@app.on_event("shutdown")
def shutdown_event():
    pipeline_simulator.stop_simulator()

# Serve static dashboard files
if not os.path.exists("static"):
    os.makedirs("static")

# Helper to send slack message in background task
def send_slack_notification(message: str):
    if SLACK_WEBHOOK_URL:
        try:
            requests.post(SLACK_WEBHOOK_URL, json={"text": message})
        except Exception as e:
            print(f"Error sending Slack alert: {e}")

# Ingestion Endpoints for real Agents

@app.post("/api/agent/telemetry")
def ingest_telemetry(data: AgentTelemetry, background_tasks: BackgroundTasks):
    conn = sqlite3.connect(pipeline_simulator.DB_NAME)
    cursor = conn.cursor()
    
    timestamp = datetime.utcnow().isoformat()
    
    # Store real telemetry
    cursor.execute(
        "INSERT INTO telemetry (timestamp, server_id, cpu_utilization, memory_utilization, disk_utilization, throughput_kbps) VALUES (?, ?, ?, ?, ?, ?)",
        (timestamp, data.server_id, data.cpu_utilization, data.memory_utilization, data.disk_utilization, data.throughput_kbps)
    )
    
    # Run alert threshold checks
    check_and_trigger_alerts(cursor, timestamp, data.server_id, "CPU", data.cpu_utilization, 50.0, "CRITICAL", background_tasks)
    check_and_trigger_alerts(cursor, timestamp, data.server_id, "Memory", data.memory_utilization, 85.0, "WARNING", background_tasks)
    
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.post("/api/agent/logs")
def ingest_logs(data: AgentLog):
    conn = sqlite3.connect(pipeline_simulator.DB_NAME)
    cursor = conn.cursor()
    
    timestamp = datetime.utcnow().isoformat()
    
    cursor.execute(
        "INSERT INTO logs (timestamp, cloud_provider, service, level, message, server_id, status_code) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (timestamp, data.cloud_provider, data.service, data.level, data.message, data.server_id, data.status_code)
    )
    
    conn.commit()
    conn.close()
    return {"status": "success"}

def check_and_trigger_alerts(cursor, timestamp, server, metric, value, threshold, severity, background_tasks):
    if value > threshold:
        cursor.execute("SELECT id FROM alerts WHERE server_id = ? AND metric = ? AND resolved = 0", (server, metric))
        existing = cursor.fetchone()
        if not existing:
            cursor.execute(
                "INSERT INTO alerts (timestamp, server_id, metric, value, severity, resolved) VALUES (?, ?, ?, ?, ?, 0)",
                (timestamp, server, metric, value, severity)
            )
            # Trigger Slack webhook if configured
            alert_msg = f"🚨 *CRITICAL ALERT* 🚨\nServer: `{server}`\nMetric: `{metric}` spiked to `{value}%` (Threshold: {threshold}%)"
            background_tasks.add_task(send_slack_notification, alert_msg)
    else:
        cursor.execute(
            "UPDATE alerts SET resolved = 1 WHERE server_id = ? AND metric = ? AND resolved = 0",
            (server, metric)
        )

# Web endpoints

@app.get("/api/status")
def get_status():
    return {
        "running": pipeline_simulator.simulator_running,
        "records_processed": pipeline_simulator.records_processed
    }

@app.post("/api/status/toggle")
def toggle_simulator(action: str):
    if action == "start":
        pipeline_simulator.start_simulator()
    elif action == "stop":
        pipeline_simulator.stop_simulator()
    return {"status": "success", "running": pipeline_simulator.simulator_running}

@app.get("/api/stats")
def get_stats():
    conn = sqlite3.connect(pipeline_simulator.DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM logs")
    total_logs = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM alerts WHERE resolved = 0")
    active_alerts = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM logs WHERE level IN ('ERROR', 'CRITICAL')")
    critical_errors = cursor.fetchone()[0]
    
    conn.close()
    
    return {
        "total_logs": total_logs,
        "active_alerts": active_alerts,
        "critical_errors": critical_errors,
        "ingestion_rate_processed": pipeline_simulator.records_processed
    }

@app.get("/api/logs")
def get_logs(
    level: str = None, 
    search: str = None, 
    provider: str = None, 
    limit: int = 50
):
    conn = sqlite3.connect(pipeline_simulator.DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    query = "SELECT * FROM logs WHERE 1=1"
    params = []
    
    if level and level != "ALL":
        query += " AND level = ?"
        params.append(level)
    if provider and provider != "ALL":
        query += " AND cloud_provider = ?"
        params.append(provider)
    if search:
        query += " AND (message LIKE ? OR server_id LIKE ?)"
        params.append(f"%{search}%")
        params.append(f"%{search}%")
        
    query += " ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    
    return [dict(row) for row in rows]

@app.get("/api/telemetry")
def get_telemetry():
    conn = sqlite3.connect(pipeline_simulator.DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Dynamically find all unique server_ids registered in telemetry
    cursor.execute("SELECT DISTINCT server_id FROM telemetry")
    servers = [row[0] for row in cursor.fetchall()]
    
    # If database is empty, fallback to simulator lists
    if not servers:
        servers = pipeline_simulator.SERVERS
        
    data = {}
    for server in servers:
        cursor.execute(
            "SELECT * FROM telemetry WHERE server_id = ? ORDER BY timestamp DESC LIMIT 20",
            (server,)
        )
        rows = cursor.fetchall()
        data[server] = [dict(row) for row in reversed(rows)]
        
    conn.close()
    return data

@app.get("/api/alerts")
def get_alerts():
    conn = sqlite3.connect(pipeline_simulator.DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM alerts ORDER BY timestamp DESC LIMIT 30")
    rows = cursor.fetchall()
    conn.close()
    
    return [dict(row) for row in rows]

@app.post("/api/inject")
def inject_incident(server: str, metric: str):
    # Support injecting on mock servers or dynamic agents
    pipeline_simulator.inject_error_event(server, metric)
    return {"status": "incident_injected", "server": server, "metric": metric}

# Mount UI Static files
app.mount("/", StaticFiles(directory="static", html=True), name="static")
