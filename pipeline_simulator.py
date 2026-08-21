import time
import random
import sqlite3
import threading
import json
from datetime import datetime

# Database setup
DB_NAME = "metrics.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Logs table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT,
        cloud_provider TEXT,
        service TEXT,
        level TEXT,
        message TEXT,
        server_id TEXT,
        status_code INTEGER
    )
    """)
    
    # Telemetry metrics table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS telemetry (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT,
        server_id TEXT,
        cpu_utilization REAL,
        memory_utilization REAL,
        disk_utilization REAL,
        throughput_kbps REAL
    )
    """)
    
    # Active alerts table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT,
        server_id TEXT,
        metric TEXT,
        value REAL,
        severity TEXT,
        resolved INTEGER DEFAULT 0
    )
    """)
    
    conn.commit()
    conn.close()

# Mock generators
CLOUD_PROVIDERS = ["Azure", "GCP"]
SERVICES = {
    "Azure": ["EventHubs", "AppService", "Synapse", "SQLServer"],
    "GCP": ["PubSub", "AppEngine", "BigQuery", "CloudSQL"]
}
LEVELS = ["INFO", "WARNING", "ERROR", "CRITICAL"]
SERVERS = ["srv-prod-east-01", "srv-prod-east-02", "srv-prod-west-01", "srv-prod-west-02", "srv-deloitte-prod-01"]

MOCK_MESSAGES = {
    "INFO": [
        "Connection established successfully.",
        "Query executed in 45ms.",
        "Batch job chunk processed.",
        "User session token refreshed.",
        "Keep-alive heartbeat received."
    ],
    "WARNING": [
        "High response latency detected (1.2s).",
        "Connection pool approaching 80% limit.",
        "Disk utilization exceeded 75% warning threshold.",
        "Minor API rate limit restriction applied."
    ],
    "ERROR": [
        "Failed to connect to database replica.",
        "Timeout error reading from event stream queue.",
        "API Request failed with status code 500.",
        "Failed to write state token to storage cache."
    ],
    "CRITICAL": [
        "Out of Memory: Pipeline execution terminated.",
        "Security threat: Multiple invalid login attempts on root SSH.",
        "Primary storage disk write failure. Read-only mode activated."
    ]
}

# Simulator control
simulator_running = False
simulator_thread = None
records_processed = 0

def run_simulator():
    global simulator_running, records_processed
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Baseline server performance configuration to simulate metrics
    server_stats = {
        srv: {"cpu": 35.0, "mem": 45.0, "disk": 60.0} for srv in SERVERS
    }
    
    while simulator_running:
        timestamp = datetime.utcnow().isoformat()
        
        # 1. Generate logs (Random count between 2 to 5 logs per second)
        num_logs = random.randint(2, 6)
        for _ in range(num_logs):
            provider = random.choice(CLOUD_PROVIDERS)
            service = random.choice(SERVICES[provider])
            server = random.choice(SERVERS)
            
            # Weighted choice: INFO (80%), WARNING (12%), ERROR (6%), CRITICAL (2%)
            level = random.choices(LEVELS, weights=[80, 12, 6, 2], k=1)[0]
            message = random.choice(MOCK_MESSAGES[level])
            
            status_code = 200
            if level == "ERROR":
                status_code = random.choice([500, 503, 400])
            elif level == "CRITICAL":
                status_code = 500
            elif level == "WARNING":
                status_code = 429
                
            cursor.execute(
                "INSERT INTO logs (timestamp, cloud_provider, service, level, message, server_id, status_code) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (timestamp, provider, service, level, message, server, status_code)
            )
            records_processed += 1

        # 2. Update and insert server telemetry
        for server in SERVERS:
            # Add small random walk to simulate metric fluctuations
            server_stats[server]["cpu"] = max(1.0, min(100.0, server_stats[server]["cpu"] + random.uniform(-5.0, 5.0)))
            server_stats[server]["mem"] = max(5.0, min(100.0, server_stats[server]["mem"] + random.uniform(-3.0, 3.0)))
            server_stats[server]["disk"] = max(10.0, min(100.0, server_stats[server]["disk"] + random.uniform(0.0, 0.05))) # disk only grows or fluctuates slightly
            
            cpu = server_stats[server]["cpu"]
            mem = server_stats[server]["mem"]
            disk = server_stats[server]["disk"]
            throughput = random.uniform(500.0, 1500.0) # KBps
            
            cursor.execute(
                "INSERT INTO telemetry (timestamp, server_id, cpu_utilization, memory_utilization, disk_utilization, throughput_kbps) VALUES (?, ?, ?, ?, ?, ?)",
                (timestamp, server, cpu, mem, disk, throughput)
            )
            
            # Check thresholds and trigger alerts
            check_alerts(cursor, timestamp, server, "CPU", cpu, 90.0, "CRITICAL")
            check_alerts(cursor, timestamp, server, "Memory", mem, 85.0, "WARNING")
            check_alerts(cursor, timestamp, server, "Disk", disk, 90.0, "CRITICAL")
            
        conn.commit()
        
        # Keep tables compact (only store last 200 telemetry points and 500 logs in the DB)
        cursor.execute("DELETE FROM telemetry WHERE id NOT IN (SELECT id FROM telemetry ORDER BY id DESC LIMIT 200)")
        cursor.execute("DELETE FROM logs WHERE id NOT IN (SELECT id FROM logs ORDER BY id DESC LIMIT 500)")
        cursor.execute("DELETE FROM alerts WHERE id NOT IN (SELECT id FROM alerts ORDER BY id DESC LIMIT 100)")
        conn.commit()
        
        time.sleep(1.0)
        
    conn.close()

def check_alerts(cursor, timestamp, server, metric, value, threshold, severity):
    if value > threshold:
        # Check if active alert already exists
        cursor.execute("SELECT id FROM alerts WHERE server_id = ? AND metric = ? AND resolved = 0", (server, metric))
        existing = cursor.fetchone()
        if not existing:
            cursor.execute(
                "INSERT INTO alerts (timestamp, server_id, metric, value, severity, resolved) VALUES (?, ?, ?, ?, ?, 0)",
                (timestamp, server, metric, value, severity)
            )
    else:
        # Resolve alert if it was active
        cursor.execute(
            "UPDATE alerts SET resolved = 1 WHERE server_id = ? AND metric = ? AND resolved = 0",
            (server, metric)
        )

def start_simulator():
    global simulator_running, simulator_thread
    if not simulator_running:
        init_db()
        simulator_running = True
        simulator_thread = threading.Thread(target=run_simulator, daemon=True)
        simulator_thread.start()

def stop_simulator():
    global simulator_running
    simulator_running = False

def inject_error_event(server, metric, severity="CRITICAL"):
    """For manual injection to show off alerts"""
    timestamp = datetime.utcnow().isoformat()
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    value = 98.5 if metric == "CPU" else 96.2
    
    # Insert log crash
    cursor.execute(
        "INSERT INTO logs (timestamp, cloud_provider, service, level, message, server_id, status_code) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (timestamp, "Azure", "AppService", "CRITICAL", f"ALERT INJECTED: Critical {metric} spike detected.", server, 500)
    )
    
    # Insert alert
    cursor.execute(
        "INSERT INTO alerts (timestamp, server_id, metric, value, severity, resolved) VALUES (?, ?, ?, ?, ?, 0)",
        (timestamp, server, metric, value, severity)
    )
    
    conn.commit()
    conn.close()
