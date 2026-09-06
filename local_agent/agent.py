"""Local Mac agent: polls the remote service for print jobs, prints via the Brother QL700, and is the
only place personal contact data is persisted (SQLite). Outbound-only, no inbound ports required."""
from __future__ import annotations

import base64
import io
import logging
import os
import sqlite3
import time
from pathlib import Path

import requests
from brother_ql.backends.helpers import send
from brother_ql.raster import BrotherQLRaster
from dotenv import load_dotenv
from PIL import Image

from shared.models import compose_label

load_dotenv(Path(__file__).parent / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("mcode-agent")

REMOTE_URL = os.environ["REMOTE_URL"].rstrip("/")
API_KEY = os.environ["AGENT_API_KEY"]
PRINTER_IDENTIFIER = os.environ.get("PRINTER_IDENTIFIER", "usb://0x04f9:0x2042")
POLL_INTERVAL_SECONDS = float(os.environ.get("POLL_INTERVAL_SECONDS", "3"))
DB_PATH = Path(os.environ.get("LOCAL_DB_PATH", str(Path(__file__).parent / "contacts.db")))

HEADERS = {"X-API-Key": API_KEY}


def init_db() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS contacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                consent INTEGER NOT NULL,
                name TEXT, company TEXT, position TEXT, email TEXT, phone TEXT, url TEXT
            )
            """
        )


def store_contact(job: dict) -> None:
    """Full record if consent was given; otherwise a minimal audit row with no personal fields."""
    consent = job["consent"]
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO contacts (job_id, created_at, consent, name, company, position, email, phone, url)
            VALUES (?, datetime('now'), ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job["id"], int(consent),
                *( (job["name"], job["company"], job["position"], job["email"], job["phone"], job["url"])
                   if consent else (None, None, None, None, None, None) ),
            ),
        )


def print_label(job: dict) -> None:
    qr_image = Image.open(io.BytesIO(base64.b64decode(job["qr_png_base64"])))
    label = compose_label(qr_image, job["name"])

    qlr = BrotherQLRaster("QL-700")
    qlr.exception_on_warning = True
    from brother_ql.conversion import convert

    instructions = convert(qlr=qlr, images=[label], label="62", rotate="0", cut=True)
    send(instructions=instructions, printer_identifier=PRINTER_IDENTIFIER, backend_identifier="pyusb")


def fetch_next_job() -> dict | None:
    resp = requests.get(f"{REMOTE_URL}/agent/jobs/next", headers=HEADERS, timeout=10)
    resp.raise_for_status()
    return resp.json()["job"]


def ack_job(job_id: str) -> None:
    resp = requests.post(f"{REMOTE_URL}/agent/jobs/{job_id}/ack", headers=HEADERS, timeout=10)
    resp.raise_for_status()


def run_forever() -> None:
    init_db()
    log.info("agent started, polling %s every %ss", REMOTE_URL, POLL_INTERVAL_SECONDS)
    while True:
        try:
            job = fetch_next_job()
            if job is None:
                time.sleep(POLL_INTERVAL_SECONDS)
                continue

            log.info("processing job %s", job["id"])
            print_label(job)
            store_contact(job)
            ack_job(job["id"])
            log.info("job %s printed, stored, acked", job["id"])
        except Exception:
            log.exception("job processing failed, will retry")
            time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    run_forever()
