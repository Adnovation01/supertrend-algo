"""
Supertrend Algo — AI-Powered Health Monitor (Gemini)
Runs every 5 minutes via Task Scheduler.
Checks port 8501, task state, and app logs.
Unknown errors are diagnosed by Gemini, which generates and applies fixes.
"""
import subprocess
import os
import sys
import datetime
import socket
import time
import traceback

from dotenv import load_dotenv
load_dotenv(dotenv_path=r"C:\supertrend-algo\.env")

LOG_FILE  = r"C:\supertrend-algo\logs\monitor.log"
APP_DIR   = r"C:\supertrend-algo"
TASK_NAME = "SupertrendAlgo"
PORT      = 8501
PYTHON    = r"C:\Program Files\Python311\python.exe"

# Known-fixable error signatures (handled locally, no AI needed)
KNOWN_ERRORS = [
    "database is locked",
    "address already in use",
    "10048",
    "ModuleNotFoundError",
    "No module named",
    "REGISTER_SECRETKEY",
]


def log(msg, level="INFO"):
    ts   = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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
    subprocess.run(
        ["powershell.exe", "-Command",
         f"Stop-ScheduledTask -TaskName '{TASK_NAME}' -ErrorAction SilentlyContinue"],
        capture_output=True, timeout=15
    )
    time.sleep(3)
    subprocess.run(
        ["powershell.exe", "-Command",
         f"Start-ScheduledTask -TaskName '{TASK_NAME}'"],
        capture_output=True, timeout=15
    )
    log(f"Issued Start-ScheduledTask for '{TASK_NAME}'", "ACTION")
    time.sleep(10)


def get_recent_app_errors(lines=100):
    app_log = os.path.join(APP_DIR, "logs", "app.log")
    if not os.path.isfile(app_log):
        return []
    try:
        with open(app_log, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
        recent = all_lines[-lines:]
        errors = [l.strip() for l in recent
                  if any(kw in l for kw in ("ERROR", "CRITICAL", "Traceback", "Exception"))]
        return errors
    except Exception as e:
        log(f"Could not read app.log: {e}", "WARN")
        return []


def get_app_source_context():
    """Collect key source files to give Gemini full context for fixes."""
    files = {
        "main.py":          os.path.join(APP_DIR, "main.py"),
        "web/__init__.py":  os.path.join(APP_DIR, "web", "__init__.py"),
        "web/models.py":    os.path.join(APP_DIR, "web", "models.py"),
        "web/tvviews.py":   os.path.join(APP_DIR, "web", "tvviews.py"),
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


def apply_gemini_fix(fix_instructions: str) -> bool:
    """
    Parse and apply fix instructions returned by Gemini.
    Gemini returns a structured block:
      FILE: <relative path>
      FIND: <exact string to find>
      REPLACE: <replacement string>
      ---
    Or a COMMAND block:
      COMMAND: <powershell command>
    """
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
            log(f"Gemini fix — running command: {cmd}", "FIX")
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
            rel_path = kv["FILE"].replace("/", os.sep).replace("\\", os.sep)
            abs_path = os.path.join(APP_DIR, rel_path)
            find_str    = kv["FIND"].replace("\\n", "\n")
            replace_str = kv["REPLACE"].replace("\\n", "\n")
            log(f"Gemini fix — patching {rel_path}", "FIX")
            try:
                with open(abs_path, "r", encoding="utf-8") as f:
                    content = f.read()
                if find_str in content:
                    new_content = content.replace(find_str, replace_str, 1)
                    with open(abs_path, "w", encoding="utf-8") as f:
                        f.write(new_content)
                    log(f"Patched {rel_path} successfully", "FIX")
                    applied = True
                else:
                    log(f"FIND string not found in {rel_path} — skipping patch", "WARN")
            except Exception as e:
                log(f"File patch failed: {e}", "ERROR")

    return applied


def ask_gemini(errors: list, source_context: dict) -> str | None:
    """Send error context to Gemini and get a structured fix back."""
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
The following Flask application is running on a Windows Server VPS and has crashed or logged errors.

PROJECT: Supertrend Algo — TradingView to MetaTrader5 bridge
LOCATION: C:\\supertrend-algo
PYTHON: C:\\Program Files\\Python311\\python.exe
PORT: 8501

=== RECENT ERRORS FROM app.log ===
{error_text}

=== SOURCE CODE CONTEXT ===
{source_dumps}

Your job: diagnose the root cause and provide SPECIFIC fix instructions.

RESPONSE FORMAT (use exactly this format, one block per fix, separated by ---):

For a file patch:
FILE: <relative path like web/models.py>
FIND: <exact string in the file to replace>
REPLACE: <replacement string>
---

For a shell command:
COMMAND: <powershell or python command to run>
---

Rules:
- Only output fix blocks, no explanation text outside the blocks
- Only suggest fixes you are confident about
- If no fix is possible, output: NO_FIX
- Keep FIND strings short and unique enough to match exactly once
- Use \\n for newlines inside FIND/REPLACE values
"""

    try:
        log("Sending error to Gemini for diagnosis...", "AI")
        response = model.generate_content(prompt)
        reply    = response.text.strip()
        log(f"Gemini response ({len(reply)} chars):\n{reply[:600]}", "AI")
        return reply
    except Exception as e:
        log(f"Gemini API call failed: {e}", "ERROR")
        return None


def apply_known_fix(error_text: str) -> bool:
    """Fast local fixes for well-known errors — no AI needed."""

    if "database is locked" in error_text.lower():
        log("Known fix: SQLite lock — removing WAL files", "FIX")
        for ext in ["-wal", "-shm"]:
            f = os.path.join(APP_DIR, "instance", "database.db" + ext)
            if os.path.isfile(f):
                os.remove(f)
                log(f"Removed {f}", "FIX")
        return True

    if "address already in use" in error_text.lower() or "10048" in error_text:
        log("Known fix: port in use — killing stale process on 8501", "FIX")
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
            with open(env_path, "w") as f:
                f.write("REGISTER_SECRETKEY=secret@2026\nSUPERUSER_USERNAME=admin\n"
                        "SUPERUSER_NAME=Admin\nSUPERUSER_PASSWORD=admin\nNGROK_ENABLED=n\n"
                        f"GEMINI_API_KEY={os.getenv('GEMINI_API_KEY','')}\n")
            return True

    return False


def rotate_log():
    if os.path.isfile(LOG_FILE) and os.path.getsize(LOG_FILE) > 5 * 1024 * 1024:
        rotated = LOG_FILE.replace(".log", "_old.log")
        if os.path.isfile(rotated):
            os.remove(rotated)
        os.rename(LOG_FILE, rotated)
        log("Monitor log rotated", "INFO")


def run():
    rotate_log()
    log("=" * 60)
    log("Health check start")

    port_ok    = is_port_listening(PORT)
    task_state = get_task_state()
    errors     = get_recent_app_errors()

    log(f"Port {PORT} listening : {port_ok}")
    log(f"Task state            : {task_state}")
    log(f"Error lines in log    : {len(errors)}")

    for e in errors[-5:]:
        log(f"  >> {e}", "WARN")

    needs_restart = False

    if not port_ok:
        log("ALERT: Port 8501 is DOWN", "ALERT")
        needs_restart = True

    if task_state not in ("Running", "Ready"):
        log(f"ALERT: Task in bad state: {task_state}", "ALERT")
        needs_restart = True

    if errors:
        error_text = "\n".join(errors)
        is_known   = any(sig in error_text for sig in KNOWN_ERRORS)

        if is_known:
            fixed = apply_known_fix(error_text)
            if fixed:
                needs_restart = True
        else:
            # Unknown error — ask Gemini
            log("Unknown error detected — escalating to Gemini AI", "AI")
            source_ctx = get_app_source_context()
            fix_reply  = ask_gemini(errors, source_ctx)

            if fix_reply and fix_reply.strip() != "NO_FIX":
                applied = apply_gemini_fix(fix_reply)
                if applied:
                    needs_restart = True
                    log("Gemini fix applied — will restart app", "ACTION")
                else:
                    log("Gemini returned a fix but it could not be applied", "WARN")
            else:
                log("Gemini could not determine a fix — manual review needed", "WARN")

    if needs_restart:
        log("Restarting SupertrendAlgo...", "ACTION")
        start_task()
        time.sleep(10)
        recovered = is_port_listening(PORT)
        if recovered:
            log("Recovery SUCCESSFUL — port 8501 is back up", "OK")
        else:
            log("Recovery FAILED — port still not listening after restart", "ERROR")
    else:
        log("All checks PASSED — app is healthy", "OK")

    log("Health check end")
    log("=" * 60 + "\n")


if __name__ == "__main__":
    run()
