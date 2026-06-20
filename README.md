# MedOffice AI

> AI-powered documentation assistant for Ontario primary care — built at **Hackers & Healers 2026** for the Ottawa Family Health Team.

MedOffice AI cuts the paperwork burden in a busy family practice to near zero. In a single session a physician can auto-fill any medical form, generate a complete outbound referral, summarise a 10-page specialist report into a clinical brief, and walk into each appointment already knowing which patient needs the most urgent attention — all without leaving the browser.

---

## The Problem

Family physicians spend 2–3 hours per day on administrative documentation — WSIB forms, insurance letters, referral packages, specialist note reviews — time that should go to patients. Paper-based workflows, fax machines, and disconnected systems make every task manual and error-prone.

## The Solution

MedOffice AI connects a physician's existing patient chart to Claude AI and surfaces three focused tools:

1. **AI Form Filler** — any form, any format, filled in seconds  
2. **Referral Checker** — outbound referral generation + inbound report summarisation  
3. **Smart Scheduler** — appointments prioritised by clinical risk so the most critical patients are seen first

---

## Features

### 🗂 AI Form Filler

- Upload any medical form as a **PDF or image** (WSIB, LTD insurance, school notes, disability certificates, specialist requisitions, and more)
- **Stage 1 — Local OCR:** PyMuPDF + Tesseract extract the raw text and layout of the form in ~1 second on-device
- **Stage 2 — Claude AI:** a single Claude Haiku call reads the OCR output, identifies every form field by purpose, and maps values from the patient's chart (demographics, diagnoses, medications, lab results, allergies, insurance info)
- Results appear as a **side-by-side diff** — original form on the left, AI-filled draft on the right — with every field colour-coded by confidence (green = high, amber = uncertain, red = low/missing)
- The physician can **edit any field inline** before clicking **Confirm & Download PDF**, which regenerates the overlay with all edits applied
- All submissions are logged to the activity feed and counted in dashboard stats

### 📨 Referral Checker

**Outbound Referral**

- Upload a blank referral letter or form template
- Select the patient from the dropdown (populated from the FHIR-like patient records)
- Claude analyzes the template fields and fills every one from the patient chart — GP info, patient demographics, OHIP number, diagnosis codes, current medications, relevant lab values, reason for referral, urgency
- Review and edit fields, then download the completed referral PDF

**Inbound Specialist Note Summariser**

- Receive a 4–10 page specialist letter or discharge summary?
- **Upload the PDF** directly or paste the text — either works
- PDF uploads go through the same OCR pipeline first, then the extracted text is sent to Claude
- Claude returns a structured brief:
  - **Clinical Summary** — one paragraph covering the key clinical picture
  - **Key Changes** — medications adjusted, diagnoses added, test results flagged
  - **Follow-up Actions** — what the GP needs to do (repeat labs, referrals, prescriptions)
  - **Missing / Unclear** — anything the specialist omitted or left ambiguous
- Designed to let a physician review a complex specialist letter in under 60 seconds

### 📅 Smart Scheduler

- Loads today's appointments from the database
- Each patient is scored by a **12-domain clinical risk scorer** that reads their FHIR-like record:

  | Domain | Key Signals |
  |---|---|
  | Diabetes | HbA1c, fasting glucose, hypoglycaemia history |
  | Cardiac | BNP, ejection fraction, recent MI, chest pain |
  | Renal | eGFR, creatinine, dialysis |
  | Mental Health | PHQ-9 score, suicide risk flag, crisis history |
  | Respiratory | FEV1, O₂ saturation, recent exacerbation |
  | Rheumatology | CRP, ESR, joint involvement |
  | Anaphylaxis | Allergen exposure, epinephrine use |
  | Prenatal | Gestational age, blood pressure, GDM |
  | Oncology | Active treatment, surveillance, recent imaging |
  | Pain | Opioid therapy, pain scale, OAT |
  | Anemia | Hemoglobin, iron studies, transfusion history |
  | Infection | Fever, elevated WBC, recent culture results |

- Appointments are grouped into **Critical Priority → Moderate Priority → Routine** with coloured section headers and animated indicators
- An **AI Suggestions** panel surfaces the top-risk patients with their primary clinical concern pulled directly from the risk scorer rationale
- Status badges (Upcoming → In Progress → Completed) are clickable inline — no modal required

### 🏠 Dashboard

- **Live stat cards:** Patients Today, Forms Completed Today, Referrals Pending — all pulled from the database in real time
- **Weekly Activity Chart:** line chart of forms filled and patients seen across the current week (Mon–Fri)
- **Recent Activity Feed:** every form fill, referral, and appointment update logged with relative timestamps and patient names
- **Module Cards:** 3D-animated launch cards for Form Filler, Referral Checker, and Scheduler — each showing live counts

### 🔐 Authentication

- Full **Sign Up / Sign In** system — no hardcoded demo credentials
- Passwords hashed with `pbkdf2_hmac` (SHA-256, 100 000 iterations + random 16-byte salt)
- Session tokens stored in `localStorage`; protected pages redirect to login if no valid session exists
- Sign-up collects: Full Name, Email, Role (Family Physician / NP / RN / Specialist / Admin), Clinic name

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Vanilla HTML/CSS/JS, Tailwind CSS, Chart.js |
| Backend | FastAPI (Python 3.11+) |
| AI | Anthropic Claude Haiku (`claude-haiku-4-5-20251001`) |
| OCR | PyMuPDF + Tesseract |
| Database | SQLite (Python stdlib `sqlite3`) |
| PDF rendering | PyMuPDF overlay engine |
| Patient records | FHIR-like JSON (`backend/fhir/patients.json`) |

---

## Project Structure

```
├── index.html           # AI Form Filler (standalone page)
├── referral.html        # Referral Checker — outbound + inbound
├── scheduler.html       # Smart Scheduler
├── dashboard.html       # Dashboard — stats, chart, activity feed
├── login.html           # Sign In / Create Account
├── auth.js              # login(), register(), requireAuth(), logout()
├── app.js               # Referral page UI logic
├── form-filler.js       # Form filler UI logic
├── styles.css           # Shared design system (index + referral)
├── sample-data.js       # Sample inbound specialist report
└── backend/
    ├── main.py                      # FastAPI app + all API routes
    ├── requirements.txt
    ├── .env                         # ANTHROPIC_API_KEY (not committed)
    ├── agent/
    │   ├── combined_filler.py       # Claude form analysis + fill (single call)
    │   ├── inbound_summarizer.py    # Claude inbound note summariser
    │   ├── field_mapper.py          # Field extraction helpers
    │   └── risk_scorer.py           # 12-domain clinical risk scorer
    ├── ocr/
    │   ├── docling_extractor.py     # PyMuPDF + Tesseract extraction
    │   └── pdf_renderer.py          # PDF pages → PNG (for side-by-side)
    ├── fhir/
    │   ├── patient_loader.py        # Patient record helpers
    │   └── patients.json            # 10 demo patients
    └── db/
        └── database.py              # Schema, seed data, auth, stats queries
```

---

## Getting Started

### Prerequisites

- Python 3.11+
- [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) installed on your system
  - macOS: `brew install tesseract`
  - Ubuntu: `sudo apt install tesseract-ocr`
- An [Anthropic API key](https://console.anthropic.com/)

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
uvicorn main:app --reload
```

The API runs at `http://localhost:8000`. The frontend is served statically from the project root — open:

```
http://localhost:8000/login.html
```

### 5. Create your account

Click **Create Account**, fill in your name, email, role, and clinic. You land on the dashboard immediately. From there, launch any tool from the module cards.

---

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/auth/register` | Create account, returns session token |
| `POST` | `/api/auth/login` | Sign in, returns session token |
| `GET` | `/api/patients` | List all patients |
| `POST` | `/api/ocr-extract` | Stage 1 — local OCR of uploaded form/PDF |
| `POST` | `/api/fill-form` | Stage 2 — Claude fills all identified fields |
| `POST` | `/api/generate-pdf` | Render approved edits onto original PDF |
| `POST` | `/api/summarize-inbound` | Claude summary of specialist note text |
| `GET` | `/api/appointments/risk-sorted` | Today's appointments sorted by clinical risk |
| `PATCH` | `/api/appointments/{id}/status` | Update appointment status |
| `GET` | `/api/dashboard/stats` | Live stat card values |
| `GET` | `/api/dashboard/chart` | Weekly forms + patients data for chart |
| `GET` | `/api/activity` | Recent activity feed items |
| `POST` | `/api/activity/log` | Log a custom activity event |

---

## Demo Patients

10 pre-loaded patients cover the range of conditions exercised by the risk scorer:

| Patient | Conditions |
|---|---|
| Sarah Khan | Type 2 Diabetes — HbA1c 9.1%, on insulin |
| Marcus Webb | WSIB workplace injury, hypertension |
| Marie Tremblay | Depression PHQ-9: 14, generalised anxiety |
| Robert Chen | COPD FEV1 48%, active smoker |
| Fatima Hassan | Prenatal 26 weeks, GDM screen pending |
| David Murphy | CKD Stage 3b — eGFR 38, protein 2+ |
| Elena Petrov | Rheumatoid arthritis — CRP 42 mg/L, on MTX |
| James Okafor | Asthma + anaphylaxis history, school epipen form |
| Louise Martin | Breast cancer surveillance, oncology liaison |
| Michael Santos | Opioid agonist therapy (OAT) monthly check-in |

---

## Built at Hackers & Healers 2026

**Ottawa, Ontario** · Ottawa Family Health Team  
Powered by [Claude AI](https://anthropic.com) · FastAPI · SQLite

> *"The best interface is no interface — just a form that fills itself."*
