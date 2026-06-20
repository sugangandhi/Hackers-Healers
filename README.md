# MedOffice AI

> AI-powered documentation assistant for Ontario primary care — built at Hackers & Healers 2026 for the Ottawa Family Health Team.

MedOffice AI eliminates the paperwork bottleneck in a busy family practice. Physicians can upload any medical form, generate referrals, summarise inbound specialist reports, and view their schedule sorted by clinical risk — all powered by Claude AI and a local FastAPI backend.

---

## Features

### AI Form Filler
Upload any medical form (WSIB, insurance, school notes, disability letters, etc.) as a PDF or image. The system runs local OCR to extract the form structure, then calls Claude Haiku to identify every field and fill it from the patient's FHIR-like chart. The doctor reviews an editable side-by-side diff and downloads the approved PDF.

### Referral Checker
- **Outbound** — upload a blank referral template, select a patient, and Claude fills every field from the chart in seconds.
- **Inbound** — upload a multi-page specialist PDF or paste the report text. Claude returns a one-paragraph clinical summary, a list of key changes, required follow-up actions, and any missing or unclear information.

### Smart Scheduler
Today's appointments are fetched and ranked by clinical risk score. A rules-based scorer evaluates 12 domains (diabetes, cardiac, renal, mental health, respiratory, rheumatology, anaphylaxis, prenatal, oncology, pain, anemia, infection) using lab values and conditions from the patient record. Appointments are grouped as **Critical → Moderate → Routine** with an AI Suggestions panel driven by the same risk data.

### Authentication
Full sign-up / sign-in system. Passwords are hashed with `pbkdf2_hmac` (100 000 iterations) and stored in SQLite. Sessions are token-based and stored in `localStorage`.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Vanilla HTML/CSS/JS, Tailwind CSS (dashboard/scheduler), Chart.js |
| Backend | FastAPI (Python 3.11+) |
| AI | Anthropic Claude Haiku (`claude-haiku-4-5-20251001`) |
| OCR | PyMuPDF + Tesseract |
| Database | SQLite (via Python `sqlite3`) |
| Patient data | FHIR-like JSON records (`backend/fhir/patients.json`) |

---

## Project Structure

```
├── index.html          # AI Form Filler
├── referral.html       # Referral Checker (outbound + inbound)
├── scheduler.html      # Smart Scheduler
├── dashboard.html      # Dashboard (stats, activity, module cards)
├── login.html          # Sign In / Create Account
├── auth.js             # Auth helpers (login, register, requireAuth, logout)
├── app.js              # Referral page logic
├── form-filler.js      # Form filler logic
├── styles.css          # Shared styles for index/referral pages
├── sample-data.js      # Sample inbound report text
└── backend/
    ├── main.py                     # FastAPI app & all API routes
    ├── requirements.txt
    ├── .env                        # ANTHROPIC_API_KEY goes here
    ├── agent/
    │   ├── combined_filler.py      # Claude form analysis + fill
    │   ├── inbound_summarizer.py   # Claude inbound note summariser
    │   ├── field_mapper.py         # Field extraction helpers
    │   └── risk_scorer.py          # 12-domain clinical risk scorer
    ├── ocr/
    │   ├── docling_extractor.py    # PyMuPDF + Tesseract OCR
    │   └── pdf_renderer.py         # PDF → PNG page renderer
    ├── fhir/
    │   ├── patient_loader.py
    │   └── patients.json           # 10 demo patients (FHIR-like)
    └── db/
        └── database.py             # SQLite schema, seed data, auth functions
```

---

## Getting Started

### Prerequisites

- Python 3.11+
- [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) installed on your system
- An Anthropic API key

### 1. Clone the repo

```bash
git clone https://github.com/sugangandhi/Hackers-Healers.git
cd Hackers-Healers
```

### 2. Set up the backend

```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Add your API key

Create `backend/.env`:

```
ANTHROPIC_API_KEY=sk-ant-...
```

### 4. Start the server

```bash
cd backend
uvicorn main:app --reload
```

The API runs at `http://localhost:8000`. The frontend is served from the same origin — open `http://localhost:8000/login.html` in your browser.

### 5. Create an account

Click **Create Account** on the login page. Enter your name, email, role, and clinic. The first signup creates your account immediately and drops you on the dashboard.

---

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/auth/register` | Create a new account |
| `POST` | `/api/auth/login` | Sign in, returns session token |
| `GET` | `/api/patients` | List all patients |
| `POST` | `/api/ocr-extract` | Stage 1 — local OCR of uploaded form |
| `POST` | `/api/fill-form` | Stage 2 — Claude fills all fields |
| `POST` | `/api/generate-pdf` | Render approved fields onto original PDF |
| `POST` | `/api/summarize-inbound` | Claude summary of specialist note |
| `GET` | `/api/appointments/risk-sorted` | Today's appointments sorted by clinical risk |
| `GET` | `/api/dashboard/stats` | Live stat card data |
| `GET` | `/api/dashboard/chart` | Weekly activity chart data |
| `GET` | `/api/activity` | Recent activity feed |

---

## Demo Patients

The system ships with 10 pre-loaded patients covering a range of conditions used by the risk scorer:

| Patient | Key Conditions |
|---|---|
| Sarah Khan | Type 2 Diabetes (HbA1c 9.1%) |
| Marcus Webb | WSIB injury, hypertension |
| Marie Tremblay | Depression (PHQ-9: 14), anxiety |
| Robert Chen | COPD (FEV1 48%), smoking |
| Fatima Hassan | Prenatal 26 weeks |
| David Murphy | CKD Stage 3b (eGFR 38) |
| Elena Petrov | Rheumatoid arthritis (CRP 42 mg/L) |
| James Okafor | Asthma + anaphylaxis history |
| Louise Martin | Breast cancer surveillance |
| Michael Santos | Opioid agonist therapy |

---

## Built at Hackers & Healers 2026

Ottawa, Ontario · Ottawa Family Health Team  
Powered by [Claude AI](https://anthropic.com) · FastAPI · SQLite
