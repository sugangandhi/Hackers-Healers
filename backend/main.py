"""
FastAPI backend for the Digital Medical Office Assistant.
"""
import io
import os
import json
import secrets
import base64
from dataclasses import asdict
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, File, Form, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ocr.docling_extractor import extract_document
from ocr.pdf_renderer import render_pdf_pages, overlay_fields, overlay_fields_on_image
from fhir.patient_loader import list_patients, get_patient, build_patient_context
from agent.combined_filler import analyze_and_fill
from db.database import (
    init_db, validate_credentials, get_appointments, update_appointment_status,
    create_appointment, log_activity, get_activity, log_form_submission,
    get_dashboard_stats, get_chart_data,
)

app = FastAPI(title="Medical Office Assistant API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# In-memory session store (demo only — resets on server restart)
_sessions: dict[str, str] = {}

# Bootstrap DB on startup
init_db()


@app.get("/api/patients")
async def get_patients():
    return {"patients": list_patients()}


@app.get("/api/health")
async def health():
    return {"status": "ok", "anthropic_key_set": bool(os.getenv("ANTHROPIC_API_KEY"))}


# ── Auth ──────────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str

@app.post("/api/auth/login")
async def auth_login(body: LoginRequest):
    if not validate_credentials(body.username, body.password):
        raise HTTPException(401, "Invalid credentials")
    token = secrets.token_urlsafe(32)
    _sessions[token] = body.username
    return {
        "token": token,
        "user": {
            "name": "Dr. Anika Patel",
            "initials": "AP",
            "role": "Family Physician",
            "clinic": "Ottawa Family Health Team",
            "cpso": "92841",
        },
    }


# ── Dashboard ─────────────────────────────────────────────────────────────────

@app.get("/api/dashboard/stats")
async def dashboard_stats():
    return get_dashboard_stats()


@app.get("/api/dashboard/chart")
async def dashboard_chart():
    return get_chart_data()


# ── Activity feed ─────────────────────────────────────────────────────────────

@app.get("/api/activity")
async def activity_feed(limit: int = 10):
    return {"items": get_activity(limit)}


class ActivityLogRequest(BaseModel):
    action: str
    description: str
    patient_name: str = ""
    patient_id: str = ""
    detail: str = ""
    color: str = "teal"

@app.post("/api/activity/log")
async def activity_log_endpoint(body: ActivityLogRequest):
    log_activity(body.action, body.description, body.patient_name,
                 body.patient_id, body.detail, body.color)
    return {"status": "logged"}


# ── Appointments ──────────────────────────────────────────────────────────────

@app.get("/api/appointments")
async def appointments_list(date: Optional[str] = None):
    return {"appointments": get_appointments(date)}


class AppointmentCreate(BaseModel):
    patient_id: str
    patient_name: str
    initials: str = ""
    time: str
    duration: int = 20
    type: str
    appointment_date: str
    color: str = "blue"
    badge: str = ""
    notes: str = ""

@app.post("/api/appointments")
async def appointments_create(body: AppointmentCreate):
    appt = create_appointment(
        body.patient_id, body.patient_name, body.initials,
        body.time, body.duration, body.type, body.appointment_date,
        body.color, body.badge, body.notes,
    )
    log_activity(
        "appointment_booked",
        f"Appointment booked",
        body.patient_name, body.patient_id,
        f"{body.time} — {body.type}",
        "teal",
    )
    return appt


class StatusUpdate(BaseModel):
    status: str

@app.patch("/api/appointments/{appt_id}/status")
async def appointments_update_status(appt_id: int, body: StatusUpdate):
    appt = update_appointment_status(appt_id, body.status)
    if appt is None:
        raise HTTPException(404, f"Appointment {appt_id} not found or invalid status")
    if body.status == "completed":
        log_activity(
            "appointment_completed",
            f"Appointment completed",
            appt["patient_name"], appt["patient_id"],
            appt["type"],
            "green",
        )
    elif body.status == "in-progress":
        log_activity(
            "appointment_started",
            f"Appointment started",
            appt["patient_name"], appt["patient_id"],
            appt["type"],
            "teal",
        )
    return appt


# ── Step 1: fast local OCR ────────────────────────────────────────────────────

@app.post("/api/ocr-extract")
async def ocr_extract_endpoint(file: UploadFile = File(...)):
    """
    Stage 1 — local only, fast (~1s).
    Extracts text via PyMuPDF + Tesseract and renders original pages as PNGs.
    Returns the raw OCR text so the client can immediately show step-1 done,
    then pass the text to /api/fill-form without re-uploading.
    """
    _check_file(file.filename)
    file_bytes = await file.read()

    try:
        doc = extract_document(file_bytes, file.filename)
    except Exception as e:
        raise HTTPException(500, f"OCR failed: {e}")

    orig_pages = _render_original(file_bytes, file.filename, doc)

    return {
        "ocr_text":     doc.full_text,
        "total_pages":  doc.total_pages,
        "original_pages": orig_pages,
    }


# ── Step 2: single Claude call — analyze + fill ───────────────────────────────

@app.post("/api/fill-form")
async def fill_form_endpoint(
    file: UploadFile = File(...),
    patient_id: str  = Form(...),
    ocr_text: str    = Form(default=""),   # pre-extracted by /api/ocr-extract
):
    """
    Stage 2 — one Claude Haiku call that both understands the form and fills it.
    If ocr_text is provided (from the two-step flow), skips local OCR.
    Stage 3 (PDF overlay rendering) also runs here.
    """
    _check_file(file.filename)
    file_bytes = await file.read()

    patient_context = build_patient_context(patient_id)
    if not patient_context:
        raise HTTPException(404, f"Patient {patient_id} not found")

    # OCR — skip if already done in step 1
    if not ocr_text:
        try:
            doc      = extract_document(file_bytes, file.filename)
            ocr_text = doc.full_text
        except Exception as e:
            raise HTTPException(500, f"OCR failed: {e}")

    # Single Claude call: analyze form structure + fill all fields
    try:
        schema, filled = analyze_and_fill(ocr_text, patient_context)
    except Exception as e:
        raise HTTPException(500, f"AI form filling failed: {e}")

    filled_dicts = [asdict(f) for f in filled]

    # Render original pages (may have been done in step 1 already, but we need
    # them here too so single-step callers still get them)
    try:
        doc_for_render = extract_document(file_bytes, file.filename)
    except Exception:
        doc_for_render = None

    orig_pages = _render_original(file_bytes, file.filename, doc_for_render) if doc_for_render else []

    # Overlay filled values on a copy of the form
    is_image = Path(file.filename).suffix.lower() in {".jpg", ".jpeg", ".png", ".tiff", ".tif"}
    try:
        if is_image:
            _, filled_pages = overlay_fields_on_image(file_bytes, filled_dicts)
        else:
            _, filled_pages = overlay_fields(file_bytes, filled_dicts)
    except Exception:
        filled_pages = []

    counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0, "MISSING": 0}
    for f in filled_dicts:
        counts[f["confidence"]] = counts.get(f["confidence"], 0) + 1

    # ── Log to DB ────────────────────────────────────────────────────────────
    patient_rec = get_patient(patient_id)
    patient_name = patient_rec["name"]["text"] if patient_rec else patient_id
    form_label = schema.form_type or "Medical form"

    log_form_submission(
        patient_id, patient_name, form_label,
        fields_filled=counts["HIGH"] + counts["MEDIUM"],
        fields_total=len(filled_dicts),
    )
    log_activity(
        "form_filled",
        f"{form_label} filled",
        patient_name, patient_id,
        f"{counts['HIGH']} fields auto-filled",
        "teal",
    )

    return {
        "form_type":          schema.form_type,
        "issuer":             schema.issuer,
        "purpose":            schema.purpose,
        "total_fields":       len(filled_dicts),
        "confidence_summary": counts,
        "filled_fields":      filled_dicts,
        "original_pages":     orig_pages,
        "filled_pages":       filled_pages,
        "status":             "DRAFT",
    }


# ── Download / generate approved PDF ─────────────────────────────────────────

@app.post("/api/generate-pdf")
async def generate_pdf_endpoint(
    file: UploadFile = File(...),
    fields_json: str = Form(...),
):
    """
    Final step: take the original file + doctor-approved field values,
    regenerate the overlay with any edits, and return a downloadable PDF.
    """
    _check_file(file.filename)
    file_bytes = await file.read()

    try:
        filled_fields = json.loads(fields_json)
    except Exception:
        raise HTTPException(400, "Invalid fields_json")

    is_image = Path(file.filename).suffix.lower() in {".jpg", ".jpeg", ".png", ".tiff", ".tif"}

    try:
        if is_image:
            filled_bytes, _ = overlay_fields_on_image(file_bytes, filled_fields)
            media_type = "image/png"
            filename   = "approved-form.png"
        else:
            filled_bytes, _ = overlay_fields(file_bytes, filled_fields)
            media_type = "application/pdf"
            filename   = "approved-form.pdf"
    except Exception as e:
        raise HTTPException(500, f"PDF generation failed: {e}")

    return StreamingResponse(
        io.BytesIO(filled_bytes),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _check_file(filename):
    if not filename:
        raise HTTPException(400, "No file provided")
    allowed = {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif"}
    if Path(filename).suffix.lower() not in allowed:
        raise HTTPException(400, f"Unsupported file type: {Path(filename).suffix}")


def _render_original(file_bytes: bytes, filename: str, doc) -> list[str]:
    is_image = Path(filename).suffix.lower() in {".jpg", ".jpeg", ".png", ".tiff", ".tif"}
    if is_image:
        return [doc.pages[0].image_b64] if doc and doc.pages else []
    try:
        return render_pdf_pages(file_bytes)
    except Exception:
        return [p.image_b64 for p in doc.pages] if doc else []


# ── Inbound summary ───────────────────────────────────────────────────────────

class InboundSummaryRequest(BaseModel):
    text: str

@app.post("/api/summarize-inbound")
async def summarize_inbound_endpoint(body: InboundSummaryRequest):
    from agent.inbound_summarizer import summarize_inbound_note
    if not body.text.strip():
        raise HTTPException(400, "No text provided")
    try:
        return summarize_inbound_note(body.text)
    except Exception as e:
        raise HTTPException(500, f"Summarization failed: {e}")


# ── Serve frontend — must be last so API routes take precedence ───────────────
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
