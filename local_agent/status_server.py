"""Tiny stdlib-only status page for the local agent: shows the remote URL and recent job events."""
from __future__ import annotations

import io
import threading
from collections import deque
from datetime import datetime, timezone
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from shared.models import build_qr_image

_events: deque[tuple[str, str, str]] = deque(maxlen=50)  # (time, job_id, message)
_lock = threading.Lock()
_remote_url = ""
_printer_identifier = ""


def configure(remote_url: str, printer_identifier: str) -> None:
    global _remote_url, _printer_identifier
    _remote_url = remote_url
    _printer_identifier = printer_identifier


def add_event(job_id: str, message: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    with _lock:
        _events.appendleft((ts, job_id, message))


def _render() -> bytes:
    with _lock:
        rows = list(_events)
    rows_html = "".join(
        f"<tr><td>{escape(ts)}</td><td>{escape(job_id)}</td><td>{escape(message)}</td></tr>"
        for ts, job_id, message in rows
    ) or "<tr><td colspan=3>No jobs processed yet</td></tr>"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta http-equiv="refresh" content="2">
  <title>Meet Code Agent Status</title>
  <style>
    body {{ font-family: sans-serif; margin: 2rem; background: #111; color: #eee; }}
    table {{ border-collapse: collapse; width: 100%; }}
    td, th {{ border-bottom: 1px solid #333; padding: 0.4rem 0.6rem; text-align: left; }}
    code {{ color: #7fd; }}
  </style>
</head>
<body>
  <h1>Meet Code &mdash; Local Agent</h1>
  <p>Polling remote: <code>{escape(_remote_url)}</code></p>
  <p>Printer: <code>{escape(_printer_identifier)}</code></p>
  <img src="/qr.png" alt="QR code for remote URL" width="200" height="200">
  <h2>Recent jobs</h2>
  <table>
    <tr><th>Time</th><th>Job</th><th>Status</th></tr>
    {rows_html}
  </table>
</body>
</html>"""
    return html.encode("utf-8")


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/qr.png":
            buf = io.BytesIO()
            build_qr_image(_remote_url).save(buf, format="PNG")
            body = buf.getvalue()
            content_type = "image/png"
        else:
            body = _render()
            content_type = "text/html; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        pass  # silence default request logging, agent.py has its own logger


def start_in_background(port: int) -> None:
    server = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
