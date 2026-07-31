import time
import subprocess
import sys
import os

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
PYTHON_EXE = os.path.join(PROJECT_DIR, ".venv", "Scripts", "python.exe")
APP_PY = os.path.join(PROJECT_DIR, "app.py")

if not os.path.exists(PYTHON_EXE):
    PYTHON_EXE = sys.executable

def run_supervisor():
    print("========================================================")
    print("  DelhiTSR Engine Process Supervisor (Always-On Mode)")
    print("========================================================")
    print(f"Project Directory: {PROJECT_DIR}")
    print(f"Python Executable: {PYTHON_EXE}")
    print("Monitoring app.py process... Auto-healing on exit.")
    print("========================================================\n")

    while True:
        timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
        print(f"[{timestamp}] Launching Flask app (app.py)...")
        try:
            proc = subprocess.Popen([PYTHON_EXE, APP_PY], cwd=PROJECT_DIR)
            proc.wait()
            timestamp_exit = time.strftime('%Y-%m-%d %H:%M:%S')
            print(f"[{timestamp_exit}] Process exited with return code {proc.returncode}. Auto-restarting in 2 seconds...")
        except Exception as e:
            print(f"[{timestamp}] Error executing process: {e}")
        time.sleep(2)

if __name__ == "__main__":
    run_supervisor()
