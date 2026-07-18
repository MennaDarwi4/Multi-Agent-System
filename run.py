"""
Convenience launcher: starts the FastAPI backend and the Streamlit frontend
together, then shuts both down on Ctrl+C.

Run:
    python run.py

Or run them separately in two terminals:
    uvicorn api:app --host 0.0.0.0 --port 8000
    streamlit run app.py
"""
from __future__ import annotations

import os
import subprocess
import sys
import time

API_PORT = int(os.getenv("API_PORT", "8000"))
STREAMLIT_PORT = int(os.getenv("STREAMLIT_PORT", "8501"))


def main() -> None:
    env = os.environ.copy()
    env.setdefault("BACKEND_URL", f"http://localhost:{API_PORT}")

    backend = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "api:app",
         "--host", "0.0.0.0", "--port", str(API_PORT)],
        env=env,
    )
    print(f"Backend (FastAPI) starting on port {API_PORT} …")
    time.sleep(3)  # give uvicorn a moment to bind

    frontend = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", "app.py",
         "--server.port", str(STREAMLIT_PORT)],
        env=env,
    )
    print(f"Frontend (Streamlit) starting on port {STREAMLIT_PORT} …")
    print("Press Ctrl+C to stop both.")

    try:
        frontend.wait()
    except KeyboardInterrupt:
        print("\nShutting down …")
    finally:
        for p in (frontend, backend):
            p.terminate()


if __name__ == "__main__":
    main()
