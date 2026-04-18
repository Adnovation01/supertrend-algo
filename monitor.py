"""
Supertrend Algo — Local Health Monitor
Runs every 5 minutes via Task Scheduler.
Checks port 8501, task state, and app logs. Auto-restarts on failure.
"""
import subprocess
import os
import sys
import datetime
import socket
import time

LOG_FILE   = r"C:\supertrend-algo\logs\monitor.log"
APP_DIR    = r"C:\supertrend-algo"
TASK_NAME  = "SupertrendAlgo"
PORT       = 8501
PYTHON     = r"C:\Program Files\Python311\python.exe"


def log(msg, level="INFO"):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{level}] {msg}"
    print(line)
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def is_port_listening(port):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=3):
            return True
    except OSError:
        return False


def get_task_state():
    try:
        result = subprocess.run(
            ["powershell.exe", "-Command",
             f"(Get-ScheduledTask -TaskName '{TASK_NAME}').State"],
            capture_output=True, text=True, timeout=15
        )
        return result.stdout.strip()
    except Exception as e:
        log(f"Could not query task state: {e}", "ERROR")
        return "Unknown"


def start_task():
    try:
        subprocess.run(
            ["powershell.exe", "-Command",
             f"Start-ScheduledTask -TaskName '{TASK_NAME}'"],
            capture_output=True, text=True, timeout=15
        )
        log(f"Issued Start-ScheduledTask for '{TASK_NAME}'", "ACTION")
        time.sleep(8)
    except Exception as e:
        log(f"Failed to start task: {e}", "ERROR")


def get_recent_app_errors(lines=80):
    app_log = os.path.join(APP_DIR, "logs", "app.log")
    if not os.path.isfile(app_log):
        return []
    try:
        with open(app_log, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
        recent = all_lines[-lines:]
        errors = [l.strip() for l in recent if "ERROR" in l or "CRITICAL" in l or "Traceback" in l]
        return errors
    except Exception as e:
        log(f"Could not read app.log: {e}", "WARN")
        return []


def diagnose_and_fix(errors):
    """
    Basic self-healing: detect known fixable issues from log errors and apply patches.
    """
    error_text = "\n".join(errors)

    # --- Fix 1: database is locked ---
    if "database is locked" in error_text.lower():
        log("Detected SQLite lock — removing stale WAL files", "FIX")
        for ext in ["-wal", "-shm"]:
            f = os.path.join(APP_DIR, "instance", "database.db" + ext)
            if os.path.isfile(f):
                os.remove(f)
                log(f"Removed {f}", "FIX")
        return True

    # --- Fix 2: port already in use ---
    if "address already in use" in error_text.lower() or "10048" in error_text:
        log("Detected port-in-use error — killing stale python process on 8501", "FIX")
        subprocess.run(
            ["powershell.exe", "-Command",
             f"Get-NetTCPConnection -LocalPort {PORT} -ErrorAction SilentlyContinue | "
             "ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"],
            capture_output=True, timeout=15
        )
        return True

    # --- Fix 3: missing module (package install drift) ---
    if "ModuleNotFoundError" in error_text or "No module named" in error_text:
        log("Detected missing module — re-running pip install", "FIX")
        subprocess.run(
            [PYTHON, "-m", "pip", "install", "-r",
             os.path.join(APP_DIR, "requirements.txt"), "-q"],
            capture_output=True, timeout=120
        )
        return True

    # --- Fix 4: .env missing ---
    if "REGISTER_SECRETKEY" in error_text or "NoneType" in error_text and "getenv" in error_text:
        env_path = os.path.join(APP_DIR, ".env")
        if not os.path.isfile(env_path):
            log(".env missing — restoring defaults", "FIX")
            with open(env_path, "w") as f:
                f.write("REGISTER_SECRETKEY=secret@2026\n")
                f.write("SUPERUSER_USERNAME=admin\n")
                f.write("SUPERUSER_NAME=Admin\n")
                f.write("SUPERUSER_PASSWORD=admin\n")
                f.write("NGROK_ENABLED=n\n")
            return True

    return False


def check_monitor_log_size():
    """Rotate monitor log if > 5MB."""
    if os.path.isfile(LOG_FILE) and os.path.getsize(LOG_FILE) > 5 * 1024 * 1024:
        rotated = LOG_FILE.replace(".log", "_old.log")
        if os.path.isfile(rotated):
            os.remove(rotated)
        os.rename(LOG_FILE, rotated)
        log("Monitor log rotated", "INFO")


def run():
    check_monitor_log_size()
    log("--- Health check start ---")

    port_ok  = is_port_listening(PORT)
    task_state = get_task_state()
    errors   = get_recent_app_errors()

    log(f"Port {PORT} listening: {port_ok}")
    log(f"Task '{TASK_NAME}' state: {task_state}")
    log(f"Recent ERROR/CRITICAL lines in app.log: {len(errors)}")

    if errors:
        for e in errors[-5:]:  # log last 5 errors
            log(f"  app.log: {e}", "WARN")

    needs_restart = False

    # Check 1: port not listening
    if not port_ok:
        log("Port 8501 is DOWN", "ALERT")
        needs_restart = True

    # Check 2: task stopped/disabled
    if task_state not in ("Running", "Ready"):
        log(f"Task is in bad state: {task_state}", "ALERT")
        needs_restart = True

    # Check 3: try to auto-fix code errors before restarting
    if errors:
        fixed = diagnose_and_fix(errors)
        if fixed:
            log("Applied auto-fix — will restart", "ACTION")
            needs_restart = True

    if needs_restart:
        log("Restarting SupertrendAlgo task...", "ACTION")
        # Stop first in case it's hanging
        subprocess.run(
            ["powershell.exe", "-Command",
             f"Stop-ScheduledTask -TaskName '{TASK_NAME}' -ErrorAction SilentlyContinue"],
            capture_output=True, timeout=15
        )
        time.sleep(3)
        start_task()

        # Verify recovery
        time.sleep(10)
        recovered = is_port_listening(PORT)
        if recovered:
            log("Recovery SUCCESSFUL — port 8501 is back up", "OK")
        else:
            log("Recovery FAILED — port still not listening after restart", "ERROR")
    else:
        log("All checks PASSED — app is healthy", "OK")

    log("--- Health check end ---\n")


if __name__ == "__main__":
    run()
