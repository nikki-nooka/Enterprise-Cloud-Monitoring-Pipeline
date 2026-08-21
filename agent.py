import time
import requests
import psutil
import socket
import random
from datetime import datetime

# Server configuration
COLLECTOR_URL = "http://127.0.0.1:8000"
SERVER_ID = f"host-{socket.gethostname()}"
PROVIDER = "Azure" # Can simulate Azure or GCP host mapping

LOG_TEMPLATES = [
    ("INFO", "Telemetry collector agent heartbeat successfully transmitted."),
    ("INFO", "Established telemetry tunnel connection state."),
    ("WARNING", "Slight network delay detected sending telemetry chunk."),
    ("INFO", "Cleared connection pool cache buffers."),
]

def collect_and_send():
    print(f"[*] Starting Cloud Monitoring Agent on {SERVER_ID}...")
    print(f"[*] Shipping logs and telemetry to: {COLLECTOR_URL}")
    print("[*] Press Ctrl+C to terminate.")
    
    while True:
        try:
            # 1. Collect real machine metrics
            cpu = psutil.cpu_percent(interval=1)
            mem = psutil.virtual_memory().percent
            disk = psutil.disk_usage('/').percent
            
            # Send real metric payload
            telemetry_data = {
                "server_id": SERVER_ID,
                "cpu_utilization": cpu,
                "memory_utilization": mem,
                "disk_utilization": disk,
                "throughput_kbps": random.uniform(250.0, 800.0)
            }
            
            # Post telemetry
            requests.post(f"{COLLECTOR_URL}/api/agent/telemetry", json=telemetry_data)
            
            # 2. Periodically send system logs
            if random.random() < 0.4:
                level, msg = random.choice(LOG_TEMPLATES)
                
                # Check for metric spike and simulate error logs
                if cpu > 85.0:
                    level = "CRITICAL"
                    msg = f"Alert: Host CPU is spiking dangerously high at {cpu}%!"
                elif mem > 80.0:
                    level = "WARNING"
                    msg = f"Alert: High RAM allocation detected. RAM utilization is {mem}%."
                
                log_data = {
                    "cloud_provider": PROVIDER,
                    "service": "AppService" if PROVIDER == "Azure" else "AppEngine",
                    "level": level,
                    "message": msg,
                    "server_id": SERVER_ID,
                    "status_code": 200 if level == "INFO" else 500
                }
                requests.post(f"{COLLECTOR_URL}/api/agent/logs", json=log_data)
            
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Shipped Telemetry - CPU: {cpu}% | RAM: {mem}% | Disk: {disk}%")
            
        except requests.exceptions.ConnectionError:
            print("[!] Connection Error: Monitoring server is down. Retrying in 5 seconds...")
            time.sleep(5)
        except Exception as e:
            print(f"[!] Error: {str(e)}")
            
        time.sleep(1.5)

if __name__ == "__main__":
    collect_and_send()
