"""
SQLite persistence layer for MedOffice AI.
All data (appointments, activity log, form submissions) lives here.
init_db() is called once at startup; everything else is called per-request.
"""
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

DB_PATH = Path(__file__).parent / "medoffice.db"

# ─── Credentials (demo only) ─────────────────────────────────────────────────
DEMO_USERS: Dict[str, str] = {"dr.patel": "medoffice2026"}

# ─── Seed: today's appointments ───────────────────────────────────────────────
_TODAY_APPTS = [
    # (patient_id, name, initials, time, duration, type, status, color, badge)
    ("pt-001", "Sarah Khan",      "SK", "08:30", 20, "Type 2 Diabetes follow-up",           "completed",   "blue",   "Diabetes"),
    ("pt-004", "Robert Chen",     "RC", "09:00", 30, "COPD management",                     "completed",   "orange", "COPD"),
    ("pt-005", "Fatima Hassan",   "FH", "09:45", 20, "Prenatal visit — 26 weeks",           "completed",   "pink",   "Prenatal"),
    ("pt-006", "David Murphy",    "DM", "10:15", 30, "CKD Stage 3b quarterly review",       "in-progress", "red",    "CKD"),
    ("pt-008", "James Okafor",    "JO", "11:00", 20, "Asthma + anaphylaxis school form",    "upcoming",    "blue",   "Asthma"),
    ("pt-002", "Marcus Webb",      "MW", "11:30", 15, "WSIB Form 8 follow-up",               "upcoming",    "orange", "WSIB"),
    ("pt-003", "Marie Tremblay",  "MT", "14:00", 30, "Mental health follow-up",             "upcoming",    "purple", "MH"),
    ("pt-007", "Elena Petrov",    "EP", "14:45", 20, "RA monitoring + labs",                "upcoming",    "blue",   "RA"),
    ("pt-009", "Louise Martin",   "LM", "15:30", 30, "Preventive care + oncology liaison",  "upcoming",    "green",  "Oncology"),
    ("pt-010", "Michael Santos",  "MS", "16:15", 20, "OAT monthly check-in",                "upcoming",    "teal",   "OAT"),
]

# Seed: activity log (seconds_ago → how old each entry is)
_SEED_ACTIVITY = [
    ("form_filled",        "WSIB Form 8 filled",           "Marcus Webb",    "pt-002", "Form Filler AI",      "teal",   120),
    ("referral_checked",   "Referral to Cardiology",       "David Murphy",   "pt-006", "Reviewed OK",         "purple", 1080),
    ("form_filled",        "Disability form completed",    "Marie Tremblay", "pt-003", "Manulife claim",      "orange", 3600),
    ("form_filled",        "Prenatal form auto-filled",    "Fatima Hassan",  "pt-005", "26 weeks GDM",        "pink",   7200),
    ("form_filled",        "School anaphylaxis plan",      "James Okafor",   "pt-008", "Nurse copy sent",     "green",  10800),
    ("referral_flagged",   "Referral to Rheumatology",     "Elena Petrov",   "pt-007", "Flagged: missing MRI","slate",  14400),
    ("referral_flagged",   "Referral to Cardiology",       "David Murphy",   "pt-006", "Flagged: no echo",    "slate",  21600),
    ("referral_flagged",   "Referral to Neurology",        "Robert Chen",    "pt-004", "Flagged: no CT",      "slate",  28800),
    ("appointment_booked", "Appointment booked",           "Sarah Khan",     "pt-001", "Diabetes follow-up",  "teal",   86400),
]

# Seed: historical week data (patients per day and forms per day Mon–Thu)
_HIST_APPT_COUNTS  = {0: 11, 1: 14, 2: 10, 3: 16}  # weekday: count
_HIST_FORM_COUNTS  = {0: 5,  1: 9,  2: 6,  3: 11}
_HIST_POOL = [
    ("pt-001","Sarah Khan","SK",20,"Diabetes follow-up","blue","Diabetes"),
    ("pt-004","Robert Chen","RC",30,"COPD management","orange","COPD"),
    ("pt-005","Fatima Hassan","FH",20,"Prenatal check","pink","Prenatal"),
    ("pt-006","David Murphy","DM",30,"CKD review","red","CKD"),
    ("pt-003","Marie Tremblay","MT",30,"Mental health","purple","MH"),
    ("pt-007","Elena Petrov","EP",20,"RA monitoring","blue","RA"),
    ("pt-002","Marcus Webb","MW",15,"WSIB follow-up","orange","WSIB"),
    ("pt-008","James Okafor","JO",20,"Asthma review","blue","Asthma"),
]


# ─── Connection helper ────────────────────────────────────────────────────────

@contextmanager
def _conn():
    c = sqlite3.connect(str(DB_PATH))
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    finally:
        c.close()


# ─── Schema ───────────────────────────────────────────────────────────────────

_SCHEMA = """
CREATE TABLE IF NOT EXISTS appointments (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id       TEXT    NOT NULL,
    patient_name     TEXT    NOT NULL,
    initials         TEXT    DEFAULT '',
    time             TEXT    NOT NULL,
    duration         INTEGER DEFAULT 20,
    type             TEXT    NOT NULL,
    appointment_date TEXT    NOT NULL,
    status           TEXT    DEFAULT 'upcoming',
    color            TEXT    DEFAULT 'blue',
    badge            TEXT    DEFAULT '',
    notes            TEXT    DEFAULT '',
    created_at       TEXT    DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS activity_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    action       TEXT NOT NULL,
    description  TEXT NOT NULL,
    patient_name TEXT DEFAULT '',
    patient_id   TEXT DEFAULT '',
    detail       TEXT DEFAULT '',
    color        TEXT DEFAULT 'teal',
    created_at   TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS form_submissions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id      TEXT NOT NULL,
    patient_name    TEXT NOT NULL,
    form_type       TEXT DEFAULT '',
    fields_filled   INTEGER DEFAULT 0,
    fields_total    INTEGER DEFAULT 0,
    submission_date TEXT DEFAULT (date('now')),
    created_at      TEXT DEFAULT (datetime('now'))
);
"""


# ─── Init & seed ──────────────────────────────────────────────────────────────

def init_db() -> None:
    """Create tables and seed demo data. Safe to call on every startup."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    with _conn() as c:
        c.executescript(_SCHEMA)

        today_str = date.today().isoformat()

        # Seed today's appointments (once per calendar day)
        if c.execute("SELECT COUNT(*) FROM appointments WHERE appointment_date=?",
                     (today_str,)).fetchone()[0] == 0:
            # Columns: patient_id,name,initials,time,duration,type,appointment_date,status,color,badge
            # _TODAY_APPTS tuple: (pid,name,initials,time,dur,type,STATUS,color,badge)
            c.executemany(
                """INSERT INTO appointments
                   (patient_id,patient_name,initials,time,duration,type,
                    appointment_date,status,color,badge)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                [(r[0],r[1],r[2],r[3],r[4],r[5],today_str,r[6],r[7],r[8])
                 for r in _TODAY_APPTS],
            )

        # Seed Mon–Thu of current week
        _seed_week(c, today_str)

        # Seed activity log (once)
        if c.execute("SELECT COUNT(*) FROM activity_log").fetchone()[0] == 0:
            now = datetime.now()
            for action, desc, pname, pid, detail, color, secs in _SEED_ACTIVITY:
                ts = (now - timedelta(seconds=secs)).strftime("%Y-%m-%d %H:%M:%S")
                c.execute(
                    """INSERT INTO activity_log
                       (action,description,patient_name,patient_id,detail,color,created_at)
                       VALUES (?,?,?,?,?,?,?)""",
                    (action, desc, pname, pid, detail, color, ts),
                )


def _seed_week(c: sqlite3.Connection, today_str: str) -> None:
    today   = date.fromisoformat(today_str)
    monday  = today - timedelta(days=today.weekday())

    for wd, appt_count in _HIST_APPT_COUNTS.items():
        day = monday + timedelta(days=wd)
        if day >= today:
            break
        ds = day.isoformat()
        if c.execute("SELECT COUNT(*) FROM appointments WHERE appointment_date=?",
                     (ds,)).fetchone()[0]:
            continue
        for i in range(appt_count):
            p = _HIST_POOL[i % len(_HIST_POOL)]
            h = 9 + (i * 30) // 60
            m = (i * 30) % 60
            c.execute(
                """INSERT INTO appointments
                   (patient_id,patient_name,initials,time,duration,type,
                    appointment_date,status,color,badge)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (p[0],p[1],p[2],f"{h:02d}:{m:02d}",p[3],p[4],ds,"completed",p[5],p[6]),
            )

    for wd, form_count in _HIST_FORM_COUNTS.items():
        day = monday + timedelta(days=wd)
        if day >= today:
            break
        ds = day.isoformat()
        if c.execute("SELECT COUNT(*) FROM form_submissions WHERE submission_date=?",
                     (ds,)).fetchone()[0]:
            continue
        for i in range(form_count):
            p = _HIST_POOL[i % len(_HIST_POOL)]
            c.execute(
                """INSERT INTO form_submissions
                   (patient_id,patient_name,form_type,fields_filled,fields_total,submission_date)
                   VALUES (?,?,?,?,?,?)""",
                (p[0],p[1],"Medical form",25,30,ds),
            )


# ─── Auth ─────────────────────────────────────────────────────────────────────

def validate_credentials(username: str, password: str) -> bool:
    return DEMO_USERS.get(username) == password


# ─── Appointments ─────────────────────────────────────────────────────────────

def get_appointments(appt_date: Optional[str] = None) -> List[Dict]:
    d = appt_date or date.today().isoformat()
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM appointments WHERE appointment_date=? ORDER BY time", (d,)
        ).fetchall()
    return [dict(r) for r in rows]


def update_appointment_status(appt_id: int, status: str) -> Optional[Dict]:
    valid = {"upcoming", "in-progress", "completed", "cancelled"}
    if status not in valid:
        return None
    with _conn() as c:
        c.execute("UPDATE appointments SET status=? WHERE id=?", (status, appt_id))
        row = c.execute("SELECT * FROM appointments WHERE id=?", (appt_id,)).fetchone()
    return dict(row) if row else None


def create_appointment(patient_id: str, patient_name: str, initials: str,
                       time: str, duration: int, appt_type: str,
                       appointment_date: str, color: str = "blue",
                       badge: str = "", notes: str = "") -> Dict:
    with _conn() as c:
        cur = c.execute(
            """INSERT INTO appointments
               (patient_id,patient_name,initials,time,duration,type,
                appointment_date,status,color,badge,notes)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (patient_id, patient_name, initials, time, duration, appt_type,
             appointment_date, "upcoming", color, badge, notes),
        )
        row = c.execute("SELECT * FROM appointments WHERE id=?", (cur.lastrowid,)).fetchone()
    return dict(row) if row else {}


# ─── Activity log ─────────────────────────────────────────────────────────────

def log_activity(action: str, description: str, patient_name: str = "",
                 patient_id: str = "", detail: str = "", color: str = "teal") -> None:
    with _conn() as c:
        c.execute(
            """INSERT INTO activity_log
               (action,description,patient_name,patient_id,detail,color)
               VALUES (?,?,?,?,?,?)""",
            (action, description, patient_name, patient_id, detail, color),
        )


def get_activity(limit: int = 10) -> List[Dict]:
    with _conn() as c:
        rows = c.execute(
            """SELECT *,
               CAST(ROUND((julianday('now') - julianday(created_at)) * 86400) AS INTEGER) AS secs_ago
               FROM activity_log ORDER BY created_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


# ─── Form submissions ─────────────────────────────────────────────────────────

def log_form_submission(patient_id: str, patient_name: str, form_type: str,
                        fields_filled: int, fields_total: int) -> None:
    with _conn() as c:
        c.execute(
            """INSERT INTO form_submissions
               (patient_id,patient_name,form_type,fields_filled,fields_total,submission_date)
               VALUES (?,?,?,?,?,?)""",
            (patient_id, patient_name, form_type, fields_filled, fields_total,
             date.today().isoformat()),
        )


# ─── Dashboard stats ──────────────────────────────────────────────────────────

def get_dashboard_stats() -> Dict[str, Any]:
    today = date.today().isoformat()
    with _conn() as c:
        patients_seen = c.execute(
            """SELECT COUNT(*) FROM appointments
               WHERE appointment_date=? AND status IN ('completed','in-progress')""", (today,)
        ).fetchone()[0]

        forms_today = c.execute(
            "SELECT COUNT(*) FROM form_submissions WHERE submission_date=?", (today,)
        ).fetchone()[0]

        pending_referrals = c.execute(
            """SELECT COUNT(*) FROM activity_log
               WHERE action='referral_flagged' AND date(created_at)=?""", (today,)
        ).fetchone()[0] or 3   # default 3 for demo if none logged yet

        completed = c.execute(
            "SELECT COUNT(*) FROM appointments WHERE appointment_date=? AND status='completed'",
            (today,),
        ).fetchone()[0]

        in_progress = c.execute(
            "SELECT COUNT(*) FROM appointments WHERE appointment_date=? AND status='in-progress'",
            (today,),
        ).fetchone()[0]

        upcoming = c.execute(
            "SELECT COUNT(*) FROM appointments WHERE appointment_date=? AND status='upcoming'",
            (today,),
        ).fetchone()[0]

        total = c.execute(
            "SELECT COUNT(*) FROM appointments WHERE appointment_date=?", (today,)
        ).fetchone()[0]

    time_saved_min = forms_today * 15

    return {
        "patients_today":    patients_seen,
        "forms_today":       forms_today,
        "pending_referrals": pending_referrals,
        "time_saved_min":    time_saved_min,
        "completed":         completed,
        "in_progress":       in_progress,
        "upcoming":          upcoming,
        "total_today":       total,
    }


def get_chart_data() -> Dict[str, Any]:
    today   = date.today()
    monday  = today - timedelta(days=today.weekday())
    labels, forms_data, patients_data = [], [], []

    with _conn() as c:
        for i in range(5):
            day = monday + timedelta(days=i)
            if day > today:
                break
            ds    = day.isoformat()
            label = day.strftime("%a %b %d")
            labels.append(label)

            forms = c.execute(
                "SELECT COUNT(*) FROM form_submissions WHERE submission_date=?", (ds,)
            ).fetchone()[0]

            patients = c.execute(
                """SELECT COUNT(*) FROM appointments
                   WHERE appointment_date=? AND status IN ('completed','in-progress')""", (ds,)
            ).fetchone()[0]

            forms_data.append(forms)
            patients_data.append(patients)

    return {"labels": labels, "forms": forms_data, "patients": patients_data}
