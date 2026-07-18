"""
Launch the Streamlit app and expose it publicly with an ngrok tunnel.

Works both locally and inside Google Colab.

Setup (once):
    pip install -r requirements.txt
    export NGROK_AUTH_TOKEN=xxxxx        # from https://dashboard.ngrok.com

Run:
    python run_ngrok.py

On Colab, run the cells in run_colab.ipynb instead (it wraps this logic).
"""
from __future__ import annotations

import os
import subprocess
import sys
import time

PORT = int(os.getenv("STREAMLIT_PORT", "8501"))


def main() -> None:
    token = os.getenv("NGROK_AUTH_TOKEN", "")
    try:
        from pyngrok import conf, ngrok
    except ImportError:
        sys.exit("pyngrok is not installed. Run: pip install pyngrok")

    if token:
        conf.get_default().auth_token = token
    else:
        print("WARNING: NGROK_AUTH_TOKEN not set. Free ngrok now requires an "
              "auth token — set it or the tunnel will fail.")

    # kill any stale tunnels
    for t in ngrok.get_tunnels():
        ngrok.disconnect(t.public_url)

    # start streamlit as a subprocess
    cmd = [
        sys.executable, "-m", "streamlit", "run", "app.py",
        "--server.port", str(PORT),
        "--server.headless", "true",
        "--server.address", "0.0.0.0",
    ]
    proc = subprocess.Popen(cmd)
    print(f"Starting Streamlit on port {PORT} …")
    time.sleep(6)  # give streamlit time to bind

    public_url = ngrok.connect(PORT, "http").public_url
    print("\n" + "=" * 60)
    print(f"  PUBLIC URL:  {public_url}")
    print("=" * 60 + "\n")
    print("Press Ctrl+C to stop.")

    try:
        proc.wait()
    except KeyboardInterrupt:
        print("\nShutting down …")
    finally:
        ngrok.kill()
        proc.terminate()


if __name__ == "__main__":
    main()
