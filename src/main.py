import argparse
import threading
import time

import httpx
import uvicorn
import webbrowser


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
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Bind port (default: 8000)")
    parser.add_argument("--no-browser", action="store_true", help="Don't auto-open browser")
    args = parser.parse_args()

    if not args.dev and not args.no_browser:
        threading.Thread(target=open_browser, args=(args.host, args.port), daemon=True).start()

    uvicorn.run("src.web.app:app", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
