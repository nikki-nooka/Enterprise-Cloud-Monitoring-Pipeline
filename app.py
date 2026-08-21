from fastapi import FastAPI, Query, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import pipeline_simulator
import os
import requests
from datetime import datetime
from sqlalchemy import create_engine, text

app = FastAPI(title="Enterprise Monitoring Pipeline API")

# Database Portability Configuration (SQLAlchemy)
DB_PATH = os.path.abspath(pipeline_simulator.DB_NAME)
DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{DB_PATH}")

# If using PostgreSQL, sqlalchemy expects psycopg2 driver
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

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

def init_db_tables():
    """Initializes schema using SQLAlchemy (compatible with both SQLite and Postgres)"""
    is_sqlite = engine.url.drivername == "sqlite"
    serial_type = "INTEGER PRIMARY KEY AUTOINCREMENT" if is_sqlite else "SERIAL PRIMARY KEY"
    
    with engine.begin() as conn:
        conn.execute(text(f"""
        CREATE TABLE IF NOT EXISTS logs (
            id {serial_type},
            timestamp VARCHAR(100),
            cloud_provider VARCHAR(50),
            service VARCHAR(50),
            level VARCHAR(20),
            message TEXT,
            server_id VARCHAR(100),
            status_code INTEGER
        )
        """))
        
        conn.execute(text(f"""
        CREATE TABLE IF NOT EXISTS telemetry (
            id {serial_type},
            timestamp VARCHAR(100),
            server_id VARCHAR(100),
            cpu_utilization REAL,
            memory_utilization REAL,
            disk_utilization REAL,
            throughput_kbps REAL
        )
        """))
        
        conn.execute(text(f"""
        CREATE TABLE IF NOT EXISTS alerts (
            id {serial_type},
            timestamp VARCHAR(100),
            server_id VARCHAR(100),
            metric VARCHAR(50),
            value REAL,
            severity VARCHAR(20),
            resolved INTEGER DEFAULT 0
        )
        """))

# Ensure database is initialized and simulator is running
@app.on_event("startup")
def startup_event():
    init_db_tables()
    # Configure the simulator to use the same connection engine
    pipeline_simulator.DB_ENGINE = engine
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
    timestamp = datetime.utcnow().isoformat()
    
    with engine.begin() as conn:
        # Store real telemetry
        conn.execute(
            text("INSERT INTO telemetry (timestamp, server_id, cpu_utilization, memory_utilization, disk_utilization, throughput_kbps) VALUES (:ts, :srv, :cpu, :mem, :disk, :tp)"),
            {"ts": timestamp, "srv": data.server_id, "cpu": data.cpu_utilization, "mem": data.memory_utilization, "disk": data.disk_utilization, "tp": data.throughput_kbps}
        )
        
        # Run alert threshold checks
        check_and_trigger_alerts(conn, timestamp, data.server_id, "CPU", data.cpu_utilization, 50.0, "CRITICAL", background_tasks)
        check_and_trigger_alerts(conn, timestamp, data.server_id, "Memory", data.memory_utilization, 85.0, "WARNING", background_tasks)
        
    return {"status": "success"}

@app.post("/api/agent/logs")
def ingest_logs(data: AgentLog):
    timestamp = datetime.utcnow().isoformat()
    
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO logs (timestamp, cloud_provider, service, level, message, server_id, status_code) VALUES (:ts, :cp, :srvc, :lvl, :msg, :srv, :sc)"),
            {"ts": timestamp, "cp": data.cloud_provider, "srvc": data.service, "lvl": data.level, "msg": data.message, "srv": data.server_id, "sc": data.status_code}
        )
    return {"status": "success"}

def check_and_trigger_alerts(conn, timestamp, server, metric, value, threshold, severity, background_tasks):
    if value > threshold:
        existing = conn.execute(
            text("SELECT id FROM alerts WHERE server_id = :srv AND metric = :met AND resolved = 0"),
            {"srv": server, "met": metric}
        ).fetchone()
        
        if not existing:
            conn.execute(
                text("INSERT INTO alerts (timestamp, server_id, metric, value, severity, resolved) VALUES (:ts, :srv, :met, :val, :sev, 0)"),
                {"ts": timestamp, "srv": server, "met": metric, "val": value, "sev": severity}
            )
            # Trigger Slack webhook if configured
            alert_msg = f"🚨 *CRITICAL ALERT* 🚨\nServer: `{server}`\nMetric: `{metric}` spiked to `{value}%` (Threshold: {threshold}%)"
            background_tasks.add_task(send_slack_notification, alert_msg)
    else:
        conn.execute(
            text("UPDATE alerts SET resolved = 1 WHERE server_id = :srv AND metric = :met AND resolved = 0"),
            {"srv": server, "met": metric}
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
    with engine.connect() as conn:
        total_logs = conn.execute(text("SELECT COUNT(*) FROM logs")).scalar()
        active_alerts = conn.execute(text("SELECT COUNT(*) FROM alerts WHERE resolved = 0")).scalar()
        critical_errors = conn.execute(text("SELECT COUNT(*) FROM logs WHERE level IN ('ERROR', 'CRITICAL')")).scalar()
    
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
    query = "SELECT timestamp, cloud_provider, service, level, message, server_id, status_code FROM logs WHERE 1=1"
    params = {}
    
    if level and level != "ALL":
        query += " AND level = :lvl"
        params["lvl"] = level
    if provider and provider != "ALL":
        query += " AND cloud_provider = :cp"
        params["cp"] = provider
    if search:
        query += " AND (message LIKE :sch OR server_id LIKE :sch)"
        params["sch"] = f"%{search}%"
        
    query += " ORDER BY timestamp DESC LIMIT :lim"
    params["lim"] = limit
    
    with engine.connect() as conn:
        result = conn.execute(text(query), params)
        rows = [dict(row._mapping) for row in result]
        
    return rows

@app.get("/api/telemetry")
def get_telemetry():
    with engine.connect() as conn:
        # Dynamically find all unique server_ids registered in telemetry
        result = conn.execute(text("SELECT DISTINCT server_id FROM telemetry"))
        servers = [row[0] for row in result]
        
        # If database is empty, fallback to simulator lists
        if not servers:
            servers = pipeline_simulator.SERVERS
            
        data = {}
        for server in servers:
            result_metrics = conn.execute(
                text("SELECT timestamp, server_id, cpu_utilization, memory_utilization, disk_utilization, throughput_kbps FROM telemetry WHERE server_id = :srv ORDER BY timestamp DESC LIMIT 20"),
                {"srv": server}
            )
            rows = [dict(row._mapping) for row in result_metrics]
            data[server] = list(reversed(rows))
        
    return data

@app.get("/api/alerts")
def get_alerts():
    with engine.connect() as conn:
        result = conn.execute(text("SELECT timestamp, server_id, metric, value, severity, resolved FROM alerts ORDER BY timestamp DESC LIMIT 30"))
        rows = [dict(row._mapping) for row in result]
    return rows

@app.post("/api/inject")
def inject_incident(server: str, metric: str):
    pipeline_simulator.inject_error_event(server, metric)
    return {"status": "incident_injected", "server": server, "metric": metric}

# Mount UI Static files
app.mount("/", StaticFiles(directory="static", html=True), name="static")
