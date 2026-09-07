"""Local Mac agent: polls the remote service for print jobs, prints via the Brother QL700, and is the
only place personal contact data is persisted (SQLite). Outbound-only, no inbound ports required."""
from __future__ import annotations

import base64
import io
import logging
import os
import sqlite3
import sys
import time
from pathlib import Path

if sys.platform == "darwin":
    # Homebrew's arm64 libusb lives outside the paths ctypes searches by default,
    # which otherwise silently resolves to a stale x86_64 libusb under /usr/local.
    os.environ.setdefault("DYLD_LIBRARY_PATH", "/opt/homebrew/lib")

import pymupdf as fitz  # rasterizes the credits PDF onto the label
import requests
from brother_ql.backends.helpers import send
from brother_ql.raster import BrotherQLRaster
from dotenv import load_dotenv
from PIL import Image

from shared.models import LABEL_WIDTH_PX, compose_label

import status_server

load_dotenv(Path(__file__).parent / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("mcode-agent")

REMOTE_URL = os.environ["REMOTE_URL"].rstrip("/")
API_KEY = os.environ["AGENT_API_KEY"]
PRINTER_IDENTIFIER = os.environ.get("PRINTER_IDENTIFIER", "usb://0x04f9:0x2042")
PRINTER_MODEL = os.environ.get("PRINTER_MODEL", "QL-700")
POLL_INTERVAL_SECONDS = float(os.environ.get("POLL_INTERVAL_SECONDS", "3"))
DB_PATH = Path(os.environ.get("LOCAL_DB_PATH", str(Path(__file__).parent / "contacts.db")))
STATUS_PORT = int(os.environ.get("STATUS_PORT", "8787"))
PDF_PREVIEW_DIR = Path(os.environ.get("PDF_PREVIEW_DIR", str(Path(__file__).parent / "print_previews")))
_credits_pdf_env = os.environ.get("CREDITS_PDF_PATH", "")
CREDITS_PDF_PATH = str(Path(__file__).parent / _credits_pdf_env) if _credits_pdf_env else ""

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


def _send_to_printer(label_image: Image.Image) -> None:
    qlr = BrotherQLRaster(PRINTER_MODEL)
    qlr.exception_on_warning = True
    from brother_ql.conversion import convert

    instructions = convert(qlr=qlr, images=[label_image], label="62", rotate="0", cut=True)
    send(instructions=instructions, printer_identifier=PRINTER_IDENTIFIER, backend_identifier="pyusb")


def print_label(job: dict) -> str:
    """Print via USB; if no printer is found, save a PDF preview instead. Returns a status message."""
    qr_image = Image.open(io.BytesIO(base64.b64decode(job["qr_png_base64"])))
    label = compose_label(qr_image, job["name"])
    if CREDITS_PDF_PATH and Path(CREDITS_PDF_PATH).exists():
        label = _append_credits(label, Path(CREDITS_PDF_PATH))

    try:
        _send_to_printer(label)
        return "printed"
    except Exception as exc:
        log.warning("printer unavailable (%s), saving PDF preview instead", exc)
        preview_path = save_pdf_preview(label, job["id"])
        return f"no printer, saved preview: {preview_path.name}"


def _append_credits(label_image: Image.Image, credits_pdf: Path) -> Image.Image:
    """Rasterize the credits PDF pages to the label width and stack them below the label,
    producing one continuous 62mm-wide image ready for the tape printer."""
    strips = [label_image]
    with fitz.open(credits_pdf) as doc:
        for page in doc:
            zoom = LABEL_WIDTH_PX / page.rect.width
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
            strips.append(Image.frombytes("RGB", (pix.width, pix.height), pix.samples))

    total_height = sum(s.height for s in strips)
    combined = Image.new("RGB", (LABEL_WIDTH_PX, total_height), "white")
    y = 0
    for strip in strips:
        combined.paste(strip, (0, y))
        y += strip.height
    return combined


def save_pdf_preview(label_image: Image.Image, job_id: str) -> Path:
    """Save the (already-combined) label image as a single-page PDF preview."""
    PDF_PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PDF_PREVIEW_DIR / f"{job_id}.pdf"
    label_image.save(out_path, "PDF")
    return out_path


def _pdf_preview_to_image(pdf_path: Path) -> Image.Image:
    with fitz.open(pdf_path) as doc:
        page = doc[0]
        zoom = LABEL_WIDTH_PX / page.rect.width
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
        return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def recover_pending_previews() -> None:
    """Retry any PDF previews saved during a prior printer outage; move successes to a "printed" subfolder."""
    if not PDF_PREVIEW_DIR.exists():
        return
    pending = sorted(PDF_PREVIEW_DIR.glob("*.pdf"))
    if not pending:
        return
    printed_dir = PDF_PREVIEW_DIR / "printed"
    printed_dir.mkdir(parents=True, exist_ok=True)
    log.info("found %d pending print preview(s) from a prior outage, retrying", len(pending))
    for pdf_path in pending:
        try:
            _send_to_printer(_pdf_preview_to_image(pdf_path))
            pdf_path.rename(printed_dir / pdf_path.name)
            log.info("recovered and printed %s", pdf_path.name)
        except Exception as exc:
            log.warning("printer still unavailable (%s), leaving pending preview(s) for next retry", exc)
            break


def fetch_next_job() -> dict | None:
    resp = requests.get(f"{REMOTE_URL}/agent/jobs/next", headers=HEADERS, timeout=10)
    resp.raise_for_status()
    return resp.json()["job"]


def ack_job(job_id: str) -> None:
    resp = requests.post(f"{REMOTE_URL}/agent/jobs/{job_id}/ack", headers=HEADERS, timeout=10)
    resp.raise_for_status()


def run_forever() -> None:
    init_db()
    status_server.configure(REMOTE_URL, PRINTER_IDENTIFIER)
    status_server.start_in_background(STATUS_PORT)
    log.info("agent started, polling %s every %ss (status: http://127.0.0.1:%s)", REMOTE_URL, POLL_INTERVAL_SECONDS, STATUS_PORT)
    recover_pending_previews()
    while True:
        try:
            job = fetch_next_job()
            if job is None:
                time.sleep(POLL_INTERVAL_SECONDS)
                continue

            log.info("processing job %s", job["id"])
            status_server.add_event(job["id"], "printing")
            print_result = print_label(job)
            store_contact(job)
            ack_job(job["id"])
            status_server.add_event(job["id"], f"{print_result}, stored, acked")
            log.info("job %s: %s, stored, acked", job["id"], print_result)
        except Exception as exc:
            status_server.add_event("?", f"failed: {exc}")
            log.exception("job processing failed, will retry")
            time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    run_forever()
