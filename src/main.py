import argparse
import threading
import time
from pathlib import Path

import httpx
import uvicorn
import webbrowser

from src.core.config import load_config
from src.web.app import create_app


def open_browser(host: str, port: int):
    """Wait for server to be ready, then open browser."""
    url = f"http://{host}:{port}"
    for _ in range(30):  # max 10 seconds
        try:
            httpx.get(f"{url}/health", timeout=1)
            break
        except Exception:
            time.sleep(0.33)
    webbrowser.open(url)


def main():
    parser = argparse.ArgumentParser(description="Surveillance Video Analyzer")
    parser.add_argument("--dev", action="store_true", help="Development mode (no frontend mount, no auto-open)")
    parser.add_argument("--host", default=None, help="Bind host (overrides config)")
    parser.add_argument("--port", type=int, default=None, help="Bind port (overrides config)")
    parser.add_argument("--no-browser", action="store_true", help="Don't auto-open browser")
    args = parser.parse_args()

    config = load_config(Path("config/default.yaml"))
    host = args.host or config.web.host
    port = args.port or config.web.port

    if not args.dev and not args.no_browser and host in ("127.0.0.1", "localhost"):
        threading.Thread(target=open_browser, args=(host, port), daemon=True).start()

    # Pass the config in explicitly: uvicorn would otherwise import the
    # module-level `app` built without one, and web.cors_origins would be
    # silently ignored.
    app = create_app(config=config)
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
