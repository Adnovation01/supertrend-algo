"""
Supertrend Algo — Production Health Monitor
- Runs every 1 minute via Task Scheduler
- 3-attempt restart with backoff
- Email alerts on down/recovery
- Gemini AI diagnosis for unknown errors
- Watchdog checks monitor is alive
"""
import subprocess
import os
import datetime
import socket
import time
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from dotenv import load_dotenv
load_dotenv(dotenv_path=r"C:\supertrend-algo\.env")

LOG_FILE      = r"C:\supertrend-algo\logs\monitor.log"
STATE_FILE    = r"C:\supertrend-algo\logs\monitor_state.txt"
APP_DIR       = r"C:\supertrend-algo"
TASK_NAME     = "SupertrendAlgo"
PORT          = 80
PYTHON        = r"C:\Program Files\Python311\python.exe"
ALERT_EMAIL   = os.getenv("ALERT_EMAIL", "adnovationllp@gmail.com")
GMAIL_USER    = os.getenv("GMAIL_USER", "")
GMAIL_PASS    = os.getenv("GMAIL_APP_PASS", "")

KNOWN_ERRORS = [
    "database is locked",
    "address already in use",
    "10048",
    "ModuleNotFoundError",
    "No module named",
    "REGISTER_SECRETKEY",
]


# ── Logging ───────────────────────────────────────────────────────────────────

def log(msg, level="INFO"):
    ts   = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{level}] {msg}"
    print(line)
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def rotate_log():
    if os.path.isfile(LOG_FILE) and os.path.getsize(LOG_FILE) > 5 * 1024 * 1024:
        rotated = LOG_FILE.replace(".log", "_old.log")
        if os.path.isfile(rotated):
            os.remove(rotated)
        os.rename(LOG_FILE, rotated)


# ── State tracking (was app up last check?) ───────────────────────────────────

def get_last_state():
    if os.path.isfile(STATE_FILE):
        with open(STATE_FILE) as f:
            return f.read().strip()
    return "unknown"


def set_state(state):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as f:
        f.write(state)


# ── Email alerts ──────────────────────────────────────────────────────────────

def send_email(subject, body):
    if not GMAIL_USER or not GMAIL_PASS:
        log("Email not configured — skipping alert", "WARN")
        return
    try:
        msg                    = MIMEMultipart()
        msg["From"]            = GMAIL_USER
        msg["To"]              = ALERT_EMAIL
        msg["Subject"]         = subject
        msg.attach(MIMEText(body, "plain"))
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=15) as s:
            s.starttls()
            s.login(GMAIL_USER, GMAIL_PASS)
            s.sendmail(GMAIL_USER, ALERT_EMAIL, msg.as_string())
        log(f"Email alert sent: {subject}", "ALERT")
    except Exception as e:
        log(f"Email send failed: {e}", "ERROR")


def alert_down(reason):
    last = get_last_state()
    if last != "down":
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        send_email(
            subject="[ALERT] Supertrend Algo is DOWN",
            body=(
                f"Your trading bot went offline at {ts}.\n\n"
                f"Reason: {reason}\n\n"
                f"The monitor is attempting automatic recovery.\n"
                f"Check logs at: C:\\supertrend-algo\\logs\\monitor.log"
            )
        )
    set_state("down")


def alert_recovered():
    last = get_last_state()
    if last == "down":
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        send_email(
            subject="[RECOVERED] Supertrend Algo is back ONLINE",
            body=(
                f"Your trading bot recovered successfully at {ts}.\n\n"
                f"Port 80 is responding normally.\n"
                f"No action needed."
            )
        )
    set_state("up")


# ── Port / task checks ────────────────────────────────────────────────────────

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


# ── Restart with 3-attempt backoff ────────────────────────────────────────────

def restart_app(reason=""):
    log(f"Restart triggered — reason: {reason}", "ACTION")
    for attempt in range(1, 4):
        log(f"Restart attempt {attempt}/3...", "ACTION")
        subprocess.run(
            ["powershell.exe", "-Command",
             f"Stop-ScheduledTask -TaskName '{TASK_NAME}' -ErrorAction SilentlyContinue"],
            capture_output=True, timeout=15
        )
        time.sleep(4)
        subprocess.run(
            ["powershell.exe", "-Command",
             f"Start-ScheduledTask -TaskName '{TASK_NAME}'"],
            capture_output=True, timeout=15
        )
        wait = 10 + (attempt - 1) * 5   # 10s, 15s, 20s
        log(f"Waiting {wait}s for app to come up...", "ACTION")
        time.sleep(wait)
        if is_port_listening(PORT):
            log(f"Recovery SUCCESS on attempt {attempt}", "OK")
            return True
        log(f"Attempt {attempt} failed — port still down", "WARN")

    log("All 3 restart attempts failed", "ERROR")
    return False


# ── App log analysis ──────────────────────────────────────────────────────────

def get_recent_app_errors(lines=100):
    app_log = os.path.join(APP_DIR, "logs", "app.log")
    if not os.path.isfile(app_log):
        return []
    try:
        with open(app_log, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
        recent = all_lines[-lines:]
        return [l.strip() for l in recent
                if any(kw in l for kw in ("ERROR", "CRITICAL", "Traceback", "Exception"))]
    except Exception as e:
        log(f"Could not read app.log: {e}", "WARN")
        return []


# ── Known fixes ───────────────────────────────────────────────────────────────

def apply_known_fix(error_text):
    if "database is locked" in error_text.lower():
        log("Known fix: SQLite lock — removing WAL files", "FIX")
        for ext in ["-wal", "-shm"]:
            f = os.path.join(APP_DIR, "instance", "database.db" + ext)
            if os.path.isfile(f):
                os.remove(f)
        return True

    if "address already in use" in error_text.lower() or "10048" in error_text:
        log("Known fix: port conflict — killing stale python on port 80", "FIX")
        subprocess.run(
            ["powershell.exe", "-Command",
             f"Get-NetTCPConnection -LocalPort {PORT} -ErrorAction SilentlyContinue | "
             "ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"],
            capture_output=True, timeout=15
        )
        return True

    if "ModuleNotFoundError" in error_text or "No module named" in error_text:
        log("Known fix: missing module — reinstalling requirements", "FIX")
        subprocess.run(
            [PYTHON, "-m", "pip", "install", "-r",
             os.path.join(APP_DIR, "requirements.txt"), "-q"],
            capture_output=True, timeout=120
        )
        return True

    if "REGISTER_SECRETKEY" in error_text:
        env_path = os.path.join(APP_DIR, ".env")
        if not os.path.isfile(env_path):
            log("Known fix: .env missing — restoring defaults", "FIX")
            gemini_key = os.getenv("GEMINI_API_KEY", "")
            with open(env_path, "w") as f:
                f.write(f"REGISTER_SECRETKEY=secret@2026\nSUPERUSER_USERNAME=admin\n"
                        f"SUPERUSER_NAME=Admin\nSUPERUSER_PASSWORD=admin\n"
                        f"NGROK_ENABLED=n\nGEMINI_API_KEY={gemini_key}\n"
                        f"ALERT_EMAIL={ALERT_EMAIL}\n")
            return True

    return False


# ── Gemini AI diagnosis ───────────────────────────────────────────────────────

def get_app_source_context():
    files = {
        "main.py":              os.path.join(APP_DIR, "main.py"),
        "web/__init__.py":      os.path.join(APP_DIR, "web", "__init__.py"),
        "web/models.py":        os.path.join(APP_DIR, "web", "models.py"),
        "web/tvviews.py":       os.path.join(APP_DIR, "web", "tvviews.py"),
        "utils/mt5_manager.py": os.path.join(APP_DIR, "utils", "mt5_manager.py"),
    }
    context = {}
    for name, path in files.items():
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                context[name] = f.read()
        except Exception:
            pass
    return context


def apply_gemini_fix(fix_instructions):
    applied = False
    blocks  = fix_instructions.strip().split("---")
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        lines = block.splitlines()
        kv    = {}
        for line in lines:
            if ":" in line:
                key, _, val = line.partition(":")
                kv[key.strip().upper()] = val.strip()

        if "COMMAND" in kv:
            cmd = kv["COMMAND"]
            log(f"Gemini fix — running: {cmd}", "FIX")
            try:
                result = subprocess.run(
                    ["powershell.exe", "-Command", cmd],
                    capture_output=True, text=True, timeout=60
                )
                log(f"Command output: {result.stdout.strip()[:300]}", "FIX")
                applied = True
            except Exception as e:
                log(f"Command failed: {e}", "ERROR")

        elif "FILE" in kv and "FIND" in kv and "REPLACE" in kv:
            rel_path    = kv["FILE"].replace("/", os.sep)
            abs_path    = os.path.join(APP_DIR, rel_path)
            find_str    = kv["FIND"].replace("\\n", "\n")
            replace_str = kv["REPLACE"].replace("\\n", "\n")
            try:
                with open(abs_path, "r", encoding="utf-8") as f:
                    content = f.read()
                if find_str in content:
                    with open(abs_path, "w", encoding="utf-8") as f:
                        f.write(content.replace(find_str, replace_str, 1))
                    log(f"Patched {rel_path}", "FIX")
                    applied = True
                else:
                    log(f"FIND string not found in {rel_path}", "WARN")
            except Exception as e:
                log(f"File patch failed: {e}", "ERROR")
    return applied


def ask_gemini(errors, source_context):
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        log("GEMINI_API_KEY not set — skipping AI diagnosis", "WARN")
        return None
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.0-flash")
    except Exception as e:
        log(f"Gemini init failed: {e}", "ERROR")
        return None

    error_text   = "\n".join(errors[-30:])
    source_dumps = "\n\n".join(
        f"=== {name} ===\n{code[:3000]}" for name, code in source_context.items()
    )
    prompt = f"""You are an expert Python/Flask developer and DevOps engineer.
The following Flask app is running on Windows Server VPS and has crashed or logged errors.

PROJECT: Supertrend Algo (TradingView to MetaTrader5 bridge)
LOCATION: C:\\supertrend-algo
PYTHON: C:\\Program Files\\Python311\\python.exe
PORT: 80

=== RECENT ERRORS ===
{error_text}

=== SOURCE CODE ===
{source_dumps}

Diagnose and provide fix instructions in this exact format only:

For a file patch:
FILE: <relative path>
FIND: <exact string to find>
REPLACE: <replacement string>
---

For a shell command:
COMMAND: <powershell command>
---

Rules:
- Output fix blocks only, no explanation text
- If no fix possible, output: NO_FIX
- Use \\n for newlines inside FIND/REPLACE
"""
    try:
        log("Sending error to Gemini for AI diagnosis...", "AI")
        response = model.generate_content(prompt)
        reply    = response.text.strip()
        log(f"Gemini response: {reply[:400]}", "AI")
        return reply
    except Exception as e:
        log(f"Gemini API call failed: {e}", "ERROR")
        return None


# ── Main check ────────────────────────────────────────────────────────────────

def run():
    rotate_log()
    log("Health check start")

    port_ok    = is_port_listening(PORT)
    task_state = get_task_state()
    errors     = get_recent_app_errors()

    log(f"Port {PORT}: {'UP' if port_ok else 'DOWN'} | Task: {task_state} | Errors: {len(errors)}")

    for e in errors[-3:]:
        log(f"  >> {e}", "WARN")

    needs_restart = False
    failure_reason = ""

    if not port_ok:
        failure_reason = "Port 80 not responding"
        log(f"ALERT: {failure_reason}", "ALERT")
        needs_restart = True

    if task_state not in ("Running", "Ready"):
        failure_reason = f"Task in bad state: {task_state}"
        log(f"ALERT: {failure_reason}", "ALERT")
        needs_restart = True

    if errors:
        error_text = "\n".join(errors)
        is_known   = any(sig in error_text for sig in KNOWN_ERRORS)

        if is_known:
            fixed = apply_known_fix(error_text)
            if fixed:
                needs_restart  = True
                failure_reason = failure_reason or "Known error auto-fixed"
        else:
            log("Unknown error — escalating to Gemini AI", "AI")
            fix_reply = ask_gemini(errors, get_app_source_context())
            if fix_reply and fix_reply.strip() != "NO_FIX":
                applied = apply_gemini_fix(fix_reply)
                if applied:
                    needs_restart  = True
                    failure_reason = failure_reason or "Gemini AI fix applied"
            else:
                log("Gemini could not determine a fix — manual review needed", "WARN")

    if needs_restart:
        alert_down(failure_reason)
        recovered = restart_app(failure_reason)
        if recovered:
            alert_recovered()
        else:
            log("CRITICAL: App did not recover after 3 attempts", "ERROR")
            send_email(
                subject="[CRITICAL] Supertrend Algo recovery FAILED",
                body=(
                    f"Automatic recovery failed after 3 attempts.\n\n"
                    f"Reason: {failure_reason}\n\n"
                    f"MANUAL INTERVENTION REQUIRED.\n"
                    f"RDP into 138.252.201.204 and check:\n"
                    f"  C:\\supertrend-algo\\logs\\app.log\n"
                    f"  C:\\supertrend-algo\\logs\\monitor.log"
                )
            )
    else:
        log("All checks PASSED — app is healthy", "OK")
        alert_recovered()

    log("Health check end\n")


if __name__ == "__main__":
    run()
