import time
import requests
import psutil
import socket
import random
import os
import threading
from datetime import datetime

# Server configuration
COLLECTOR_URL = "http://127.0.0.1:8000"
SERVER_ID = f"host-{socket.gethostname()}"
PROVIDER = "Azure"
LOG_FILE = "app.log"

LOG_TEMPLATES = [
    ("INFO", "Telemetry collector agent heartbeat successfully transmitted."),
    ("INFO", "Established telemetry tunnel connection state."),
    ("WARNING", "Slight network delay detected sending telemetry chunk."),
    ("INFO", "Cleared connection pool cache buffers."),
]

def append_dummy_logs():
    """Simulates local application logging to app.log"""
    while True:
        try:
            level, message = random.choice(LOG_TEMPLATES)
            timestamp = datetime.now().isoformat()
            log_line = f"{timestamp} [{level}] {message}\n"
            
            with open(LOG_FILE, "a") as f:
                f.write(log_line)
        except Exception as e:
            print(f"[!] Error writing log: {e}")
        time.sleep(random.uniform(2.0, 5.0))

def tail_log_file():
    """Tails app.log and streams new lines to the FastAPI collector"""
    print(f"[*] Monitoring log file: {LOG_FILE} for changes...")
    
    # Initialize file if not exists
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as f:
            f.write(f"{datetime.now().isoformat()} [INFO] Initialized log tail file.\n")
            
    with open(LOG_FILE, "r") as f:
        # Go to the end of the file
        f.seek(0, os.SEEK_END)
        
        while True:
            line = f.readline()
            if not line:
                time.sleep(0.5)
                continue
                
            # Parse line (Format: Timestamp [LEVEL] Message)
            try:
                parts = line.strip().split(" ", 2)
                if len(parts) >= 3:
                    timestamp_str, level_raw, message = parts
                    level = level_raw.strip("[]")
                    
                    log_payload = {
                        "cloud_provider": PROVIDER,
                        "service": "AppService",
                        "level": level,
                        "message": f"[LOG HARVESTER] {message}",
                        "server_id": SERVER_ID,
                        "status_code": 200 if level == "INFO" else 500
                    }
                    requests.post(f"{COLLECTOR_URL}/api/agent/logs", json=log_payload)
            except Exception as e:
                # Fallback: post raw line
                try:
                    requests.post(f"{COLLECTOR_URL}/api/agent/logs", json={
                        "cloud_provider": PROVIDER,
                        "service": "AppService",
                        "level": "INFO",
                        "message": f"[RAW HARVESTER] {line.strip()}",
                        "server_id": SERVER_ID,
                        "status_code": 200
                    })
                except Exception as ex:
                    pass

def collect_telemetry():
    """Collects host machine hardware stats and pushes to server"""
    print(f"[*] Starting Cloud Monitoring Agent on {SERVER_ID}...")
    print(f"[*] Shipping metrics to: {COLLECTOR_URL}")
    print("[*] Press Ctrl+C to terminate.")
    
    while True:
        try:
            # Collect real machine metrics
            cpu = psutil.cpu_percent(interval=1)
            mem = psutil.virtual_memory().percent
            disk = psutil.disk_usage('/').percent
            
            telemetry_data = {
                "server_id": SERVER_ID,
                "cpu_utilization": cpu,
                "memory_utilization": mem,
                "disk_utilization": disk,
                "throughput_kbps": random.uniform(250.0, 800.0)
            }
            
            requests.post(f"{COLLECTOR_URL}/api/agent/telemetry", json=telemetry_data)
            
            # Auto-alert logging if resource spikes
            if cpu > 50.0:
                with open(LOG_FILE, "a") as f:
                    f.write(f"{datetime.now().isoformat()} [CRITICAL] Alert: Host CPU spike detected at {cpu}%!\n")
            elif mem > 80.0:
                with open(LOG_FILE, "a") as f:
                    f.write(f"{datetime.now().isoformat()} [WARNING] Alert: High memory usage: {mem}%\n")
                    
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Shipped Telemetry - CPU: {cpu}% | RAM: {mem}% | Disk: {disk}%")
            
        except requests.exceptions.ConnectionError:
            print("[!] Connection Error: Monitoring server is down. Retrying in 5 seconds...")
            time.sleep(5)
        except Exception as e:
            print(f"[!] Error: {str(e)}")
            
        time.sleep(1.5)

if __name__ == "__main__":
    # Start log generator thread
    log_gen_thread = threading.Thread(target=append_dummy_logs, daemon=True)
    log_gen_thread.start()
    
    # Start log tailer thread
    log_tailer_thread = threading.Thread(target=tail_log_file, daemon=True)
    log_tailer_thread.start()
    
    # Run telemetry collector in main thread
    collect_telemetry()
