"""Transient job queue: remote holds submitted contacts only until the local agent acks/deletes them."""
from __future__ import annotations

import base64
import io
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from shared.models import ContactData

DB_PATH = Path(__file__).parent / "pending_jobs.db"
JOB_TTL_SECONDS = 300


def init_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS pending_jobs (
                id TEXT PRIMARY KEY,
                created_at REAL NOT NULL,
                expires_at REAL NOT NULL,
                name TEXT NOT NULL,
                company TEXT, position TEXT, email TEXT, phone TEXT, url TEXT,
                consent INTEGER NOT NULL,
                qr_png BLOB NOT NULL
            )
            """
        )


@contextmanager
def _connect():
    conn = sqlite3.connect(DB_PATH)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def create_job(contact: ContactData, qr_image) -> str:
    job_id = uuid.uuid4().hex
    buf = io.BytesIO()
    qr_image.save(buf, format="PNG")
    now = time.time()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO pending_jobs
                (id, created_at, expires_at, name, company, position, email, phone, url, consent, qr_png)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_id, now, now + JOB_TTL_SECONDS,
                contact.name, contact.company, contact.position, contact.email, contact.phone, contact.url,
                int(contact.consent), buf.getvalue(),
            ),
        )
    return job_id


def get_qr_png(job_id: str) -> bytes | None:
    with _connect() as conn:
        row = conn.execute("SELECT qr_png FROM pending_jobs WHERE id = ?", (job_id,)).fetchone()
    return row[0] if row else None


def fetch_next_job() -> dict | None:
    """Return the oldest non-expired job as a JSON-serializable dict, or None."""
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT id, name, company, position, email, phone, url, consent, qr_png
            FROM pending_jobs
            WHERE expires_at > ?
            ORDER BY created_at ASC
            LIMIT 1
            """,
            (time.time(),),
        ).fetchone()
    if not row:
        return None
    job_id, name, company, position, email, phone, url, consent, qr_png = row
    return {
        "id": job_id,
        "name": name, "company": company, "position": position,
        "email": email, "phone": phone, "url": url,
        "consent": bool(consent),
        "qr_png_base64": base64.b64encode(qr_png).decode("ascii"),
    }


def delete_job(job_id: str) -> bool:
    with _connect() as conn:
        cur = conn.execute("DELETE FROM pending_jobs WHERE id = ?", (job_id,))
    return cur.rowcount > 0


def purge_expired() -> int:
    with _connect() as conn:
        cur = conn.execute("DELETE FROM pending_jobs WHERE expires_at <= ?", (time.time(),))
    return cur.rowcount
