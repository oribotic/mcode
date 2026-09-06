"""Remote public web service: collects contact + GDPR consent, queues a transient print job."""
from __future__ import annotations

import asyncio
import os

from fastapi import FastAPI, Form, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from remote import db
from shared.models import ContactData, build_qr_image, build_vcard

API_KEY = os.environ.get("AGENT_API_KEY", "")
if not API_KEY:
    raise RuntimeError("AGENT_API_KEY must be set (shared secret for the local print agent)")

limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="Meet Code")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))
app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")


@app.on_event("startup")
async def start_purge_loop() -> None:
    db.init_db()

    async def _loop():
        while True:
            db.purge_expired()
            await asyncio.sleep(30)

    asyncio.create_task(_loop())


def _require_agent_key(request: Request) -> None:
    if request.headers.get("X-API-Key") != API_KEY:
        raise HTTPException(status_code=401, detail="invalid API key")


@app.get("/", response_class=HTMLResponse)
async def splash(request: Request):
    return templates.TemplateResponse(request, "splash.html")


@app.get("/consent", response_class=HTMLResponse)
async def consent(request: Request):
    return templates.TemplateResponse(request, "consent.html")


@app.get("/form", response_class=HTMLResponse)
async def form(request: Request, consent: str = "0"):
    return templates.TemplateResponse(request, "form.html", {"consent": consent})


@app.post("/submit", response_class=HTMLResponse)
@limiter.limit("5/minute")
async def submit(
    request: Request,
    name: str = Form(...),
    company: str = Form(""),
    position: str = Form(""),
    email: str = Form(""),
    phone: str = Form(""),
    url: str = Form(""),
    consent: str = Form("0"),
):
    name = name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="name is required")

    contact = ContactData(
        name=name, company=company.strip(), position=position.strip(),
        email=email.strip(), phone=phone.strip(), url=url.strip(),
        consent=consent == "1",
    )
    vcard = build_vcard(contact)
    qr_image = build_qr_image(vcard)
    job_id = db.create_job(contact, qr_image)
    return templates.TemplateResponse(request, "generate.html", {"job_id": job_id, "name": contact.name})


@app.get("/qr/{job_id}.png")
async def qr_png(job_id: str):
    png = db.get_qr_png(job_id)
    if png is None:
        raise HTTPException(status_code=404, detail="job not found or expired")
    return Response(content=png, media_type="image/png")


@app.get("/agent/jobs/next")
async def agent_next_job(request: Request):
    _require_agent_key(request)
    job = db.fetch_next_job()
    return {"job": job}


@app.post("/agent/jobs/{job_id}/ack")
async def agent_ack_job(request: Request, job_id: str):
    _require_agent_key(request)
    deleted = db.delete_job(job_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="job not found")
    return {"ok": True}
