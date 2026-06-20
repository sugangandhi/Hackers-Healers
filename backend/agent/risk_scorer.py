"""
Rule-based clinical risk scorer.

For each patient, reads structured lab values, vitals, functional assessments,
and returns confidence-scored RiskScore objects for each clinical domain.
Thresholds are based on Canadian clinical practice guidelines.
"""
import re
from typing import Any, Dict, List, Optional

LEVEL_ORDER = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}

ICONS = {
    "Diabetes / Metabolic":         "🩸",
    "Cardiovascular":               "❤️",
    "Renal":                        "🫘",
    "Renal / Electrolytes":         "🫘",
    "Mental Health":                "🧠",
    "Respiratory":                  "🫁",
    "Rheumatology":                 "🦴",
    "Inflammation":                 "🔥",
    "Allergy / Anaphylaxis":        "⚠️",
    "Prenatal / GDM":               "🤰",
    "Prenatal / Pre-eclampsia":     "🤰",
    "Oncology Surveillance":        "🎗️",
    "Musculoskeletal / Pain":       "🩹",
    "Hematology":                   "🩸",
    "Infectious Disease":           "🦠",
}


# ── Data types ────────────────────────────────────────────────────────────────

class RiskScore:
    def __init__(self, name: str, category: str, level: str,
                 value: str, unit: str, rationale: str):
        self.name      = name
        self.category  = category
        self.level     = level       # "HIGH" | "MEDIUM" | "LOW"
        self.value     = value
        self.unit      = unit
        self.rationale = rationale
        self.icon      = ICONS.get(category, "⚕")

    def to_dict(self) -> dict:
        return {
            "name":      self.name,
            "category":  self.category,
            "level":     self.level,
            "value":     self.value,
            "unit":      self.unit,
            "rationale": self.rationale,
            "icon":      self.icon,
        }


# ── Parsing helpers ───────────────────────────────────────────────────────────

def _num(s: Any) -> Optional[float]:
    """Extract first floating-point number from any string/value."""
    if s is None:
        return None
    try:
        return float(str(s).split()[0].replace("<", "").replace(">", "").strip())
    except (ValueError, IndexError):
        m = re.search(r"\d+\.?\d*", str(s))
        return float(m.group()) if m else None


def _labs(patient: dict) -> dict:
    """Return {lowercase_test_name: lab_record}."""
    return {
        lab.get("test", "").lower().strip(): lab
        for lab in patient.get("labs", [])
    }


def _bp(patient: dict) -> tuple[Optional[int], Optional[int]]:
    v   = patient.get("vitals_trend", [{}])
    bps = v[0].get("bp", "") if v else ""
    p   = bps.split("/")
    try:
        return int(p[0]), int(p[1])
    except Exception:
        return None, None


def _peak_flow_pct(patient: dict) -> Optional[float]:
    v  = patient.get("vitals_trend", [{}])
    pf = v[0].get("peak_flow", "") if v else ""
    m  = re.search(r"(\d+)%", str(pf))
    return float(m.group(1)) if m else None


def _spo2(patient: dict) -> Optional[float]:
    v = patient.get("vitals_trend", [{}])
    s = v[0].get("o2_sat", "") if v else ""
    return _num(s)


def _has_condition(patient: dict, *keywords: str) -> bool:
    text = " ".join(c.get("display", "").lower() for c in patient.get("conditions", []))
    return any(k.lower() in text for k in keywords)


# ── Domain scorers ────────────────────────────────────────────────────────────

def _diabetes(patient: dict, labs: dict) -> List[RiskScore]:
    out = []

    # HbA1c
    lab = labs.get("hba1c")
    if lab:
        v = _num(lab.get("value"))
        if v is not None:
            if v >= 9.0:   lv, r = "HIGH",   f"HbA1c {v}% — poor glycaemic control (target < 7.0%)"
            elif v >= 7.5: lv, r = "MEDIUM", f"HbA1c {v}% — sub-optimal control"
            else:          lv, r = "LOW",    f"HbA1c {v}% — near target"
            out.append(RiskScore("HbA1c — Diabetes Control",
                                 "Diabetes / Metabolic", lv, f"{v}%", "%", r))

    # Fasting glucose
    for k in ("fasting glucose", "glucose", "fasting blood glucose"):
        lab = labs.get(k)
        if lab:
            v = _num(lab.get("value"))
            if v is not None:
                if v > 11.0:   lv, r = "HIGH",   f"Fasting glucose {v} mmol/L — severely elevated"
                elif v > 7.0:  lv, r = "MEDIUM", f"Fasting glucose {v} mmol/L — above target (7.0)"
                else:          lv, r = "LOW",    f"Fasting glucose {v} mmol/L — at target"
                out.append(RiskScore("Fasting Blood Glucose",
                                     "Diabetes / Metabolic", lv, f"{v}", "mmol/L", r))
            break

    return out


def _cardiac(patient: dict, labs: dict) -> List[RiskScore]:
    out = []

    # BNP — heart failure marker
    lab = labs.get("bnp")
    if lab:
        v = _num(lab.get("value"))
        if v is not None:
            if v > 400:    lv, r = "HIGH",   f"BNP {v} pg/mL — significant cardiac stress (HF likely)"
            elif v > 100:  lv, r = "MEDIUM", f"BNP {v} pg/mL — elevated, monitor for HF"
            else:          lv, r = "LOW",    f"BNP {v} pg/mL — normal range"
            out.append(RiskScore("BNP — Cardiac Stress", "Cardiovascular", lv, f"{v}", "pg/mL", r))

    # Troponin I
    for k in ("troponin i", "troponin"):
        lab = labs.get(k)
        if lab:
            v = _num(lab.get("value"))
            if v is not None:
                if v > 0.04:   lv, r = "HIGH",   f"Troponin I {v} — possible myocardial injury"
                elif v > 0.01: lv, r = "MEDIUM", f"Troponin I {v} — borderline, trend required"
                else:          lv, r = "LOW",    f"Troponin I {v} — within normal"
                out.append(RiskScore("Troponin I — MI Risk", "Cardiovascular",
                                     lv, f"{v}", "µg/L", r))
            break

    # Blood pressure
    sbp, dbp = _bp(patient)
    if sbp is not None:
        has_dm  = _has_condition(patient, "diabetes")
        has_ckd = _has_condition(patient, "kidney", "renal")
        target  = 120 if (has_dm or has_ckd) else 140
        if sbp >= 160 or (dbp or 0) >= 100:
            lv, r = "HIGH",   f"BP {sbp}/{dbp} mmHg — stage 2 hypertension"
        elif sbp > target:
            lv, r = "MEDIUM", f"BP {sbp}/{dbp} mmHg — above target ({target}/90)"
        else:
            lv, r = "LOW",    f"BP {sbp}/{dbp} mmHg — controlled"
        out.append(RiskScore("Blood Pressure", "Cardiovascular", lv,
                             f"{sbp}/{dbp}", "mmHg", r))

    # LDL cholesterol
    for k in ("ldl cholesterol", "ldl"):
        lab = labs.get(k)
        if lab:
            v = _num(lab.get("value"))
            if v is not None:
                has_cad = _has_condition(patient, "coronary", "atherosclerotic")
                target  = 1.8 if has_cad else (2.0 if has_dm else 3.0)
                if v > 4.0:    lv, r = "HIGH",   f"LDL {v} mmol/L — far above target ({target})"
                elif v > target: lv, r = "MEDIUM", f"LDL {v} mmol/L — above target ({target})"
                else:           lv, r = "LOW",    f"LDL {v} mmol/L — at target"
                out.append(RiskScore("LDL Cholesterol", "Cardiovascular",
                                     lv, f"{v}", "mmol/L", r))
            break

    return out


def _kidney(patient: dict, labs: dict) -> List[RiskScore]:
    out = []

    lab = labs.get("egfr")
    if lab:
        v = _num(lab.get("value"))
        if v is not None:
            if v < 30:    lv, r = "HIGH",   f"eGFR {v} mL/min — Stage 4 CKD, urgent nephrology referral"
            elif v < 60:  lv, r = "MEDIUM", f"eGFR {v} mL/min — Stage 3 CKD, monitor closely"
            else:         lv, r = "LOW",    f"eGFR {v} mL/min — normal kidney function"
            out.append(RiskScore("eGFR — Kidney Filtration", "Renal",
                                 lv, f"{v}", "mL/min/1.73m²", r))

    lab = labs.get("creatinine")
    if lab:
        v = _num(lab.get("value"))
        if v is not None:
            if v > 200:    lv, r = "HIGH",   f"Creatinine {v} µmol/L — severely elevated"
            elif v > 120:  lv, r = "MEDIUM", f"Creatinine {v} µmol/L — above normal (110)"
            else:          lv, r = "LOW",    f"Creatinine {v} µmol/L — normal"
            out.append(RiskScore("Creatinine", "Renal", lv, f"{v}", "µmol/L", r))

    for k in ("urine acr", "acr"):
        lab = labs.get(k)
        if lab:
            v = _num(lab.get("value"))
            if v is not None:
                if v > 300:   lv, r = "HIGH",   f"Urine ACR {v} mg/g — macroalbuminuria, rapid CKD progression risk"
                elif v > 30:  lv, r = "MEDIUM", f"Urine ACR {v} mg/g — microalbuminuria"
                else:         lv, r = "LOW",    f"Urine ACR {v} mg/g — normal"
                out.append(RiskScore("Urine ACR — Kidney Damage", "Renal",
                                     lv, f"{v}", "mg/g", r))
            break

    lab = labs.get("potassium")
    if lab:
        v = _num(lab.get("value"))
        if v is not None:
            if v > 5.5:   lv, r = "HIGH",   f"K⁺ {v} mmol/L — hyperkalemia, arrhythmia risk"
            elif v > 5.0: lv, r = "MEDIUM", f"K⁺ {v} mmol/L — borderline high (CKD monitoring)"
            elif v < 3.5: lv, r = "MEDIUM", f"K⁺ {v} mmol/L — hypokalemia"
            else:         lv, r = "LOW",    f"K⁺ {v} mmol/L — normal"
            out.append(RiskScore("Serum Potassium", "Renal / Electrolytes",
                                 lv, f"{v}", "mmol/L", r))

    return out


def _mental_health(patient: dict, labs: dict) -> List[RiskScore]:
    out = []
    fs = patient.get("functional_status", {})

    for field, label, max_score in (
        ("phq9_score", "PHQ-9 — Depression Severity", 27),
        ("gad7_score", "GAD-7 — Anxiety Severity",    21),
    ):
        raw = fs.get(field, "")
        if not raw:
            continue
        v = _num(raw)
        if v is None:
            continue
        cat = "Depression" if "phq" in field else "Anxiety"
        if v >= 20:    lv, r = "HIGH",   f"{label.split('—')[0].strip()} {int(v)} — severe {cat}"
        elif v >= 10:  lv, r = "MEDIUM", f"{label.split('—')[0].strip()} {int(v)} — moderate {cat}"
        else:          lv, r = "LOW",    f"{label.split('—')[0].strip()} {int(v)} — mild / none"
        out.append(RiskScore(label, "Mental Health", lv,
                             f"{int(v)}", f"/{max_score}", r))

    return out


def _respiratory(patient: dict, labs: dict) -> List[RiskScore]:
    out = []

    spo2 = _spo2(patient)
    if spo2:
        if spo2 < 92:   lv, r = "HIGH",   f"SpO2 {spo2}% — hypoxia, urgent"
        elif spo2 < 95: lv, r = "MEDIUM", f"SpO2 {spo2}% — low, monitor closely"
        else:           lv, r = "LOW",    f"SpO2 {spo2}% — normal"
        out.append(RiskScore("Oxygen Saturation (SpO2)", "Respiratory",
                             lv, f"{spo2}%", "%", r))

    pf = _peak_flow_pct(patient)
    if pf:
        if pf < 50:   lv, r = "HIGH",   f"Peak flow {pf}% predicted — severe obstruction"
        elif pf < 80: lv, r = "MEDIUM", f"Peak flow {pf}% predicted — moderate obstruction"
        else:         lv, r = "LOW",    f"Peak flow {pf}% predicted — near normal"
        out.append(RiskScore("Peak Flow — Airway Function", "Respiratory",
                             lv, f"{pf}%", "% predicted", r))

    return out


def _rheumatology(patient: dict, labs: dict) -> List[RiskScore]:
    out = []
    fa = patient.get("functional_assessment_ra", {})

    for k in ("das28_crp", "das28"):
        raw = fa.get(k, "")
        if raw:
            v = _num(raw)
            if v is not None:
                if v > 5.1:   lv, r = "HIGH",   f"DAS28-CRP {v} — active RA, DMARD review urgently needed"
                elif v > 3.2: lv, r = "MEDIUM", f"DAS28-CRP {v} — moderate disease activity"
                else:         lv, r = "LOW",    f"DAS28-CRP {v} — remission / low activity"
                out.append(RiskScore("DAS28-CRP — RA Disease Activity",
                                     "Rheumatology", lv, str(v), "score", r))
            break

    for k in ("crp", "c-reactive protein"):
        lab = labs.get(k)
        if lab:
            v = _num(lab.get("value"))
            if v is not None:
                if v > 50:   lv, r = "HIGH",   f"CRP {v} mg/L — severe systemic inflammation"
                elif v > 10: lv, r = "MEDIUM", f"CRP {v} mg/L — elevated inflammation"
                else:        lv, r = "LOW",    f"CRP {v} mg/L — normal"
                out.append(RiskScore("CRP — Inflammatory Marker",
                                     "Inflammation", lv, f"{v}", "mg/L", r))
            break

    return out


def _anaphylaxis(patient: dict, labs: dict) -> List[RiskScore]:
    out = []

    lab = labs.get("total ige")
    if lab:
        v = _num(lab.get("value"))
        if v is not None:
            if v > 1000:  lv, r = "HIGH",   f"Total IgE {v} kU/L — extreme allergic sensitization"
            elif v > 200: lv, r = "HIGH",   f"Total IgE {v} kU/L — severely elevated, anaphylaxis risk"
            elif v > 60:  lv, r = "MEDIUM", f"Total IgE {v} kU/L — elevated"
            else:         lv, r = "LOW",    f"Total IgE {v} kU/L — within range"
            out.append(RiskScore("Total IgE — Allergic Sensitization",
                                 "Allergy / Anaphylaxis", lv, f"{v}", "kU/L", r))

    for k in ("specific ige — peanut (f13)", "specific ige peanut", "peanut ige"):
        lab = labs.get(k)
        if lab:
            v = _num(lab.get("value"))
            if v is not None:
                if v >= 3.5:  lv, r = "HIGH",   f"Peanut IgE {v} kU/L — Class 3+, anaphylaxis risk HIGH"
                elif v >= 0.7: lv, r = "MEDIUM", f"Peanut IgE {v} kU/L — Class 2, sensitized"
                else:          lv, r = "LOW",    f"Peanut IgE {v} kU/L — Class 1"
                out.append(RiskScore("Peanut-Specific IgE — Anaphylaxis",
                                     "Allergy / Anaphylaxis", lv, f"{v}", "kU/L", r))
            break

    return out


def _prenatal(patient: dict, labs: dict) -> List[RiskScore]:
    out = []

    for k in ("1-hour gct (glucose challenge)", "glucose challenge", "gct"):
        lab = labs.get(k)
        if lab:
            v = _num(lab.get("value"))
            if v is not None:
                if v > 10.0:  lv, r = "HIGH",   f"GCT {v} mmol/L — GDM confirmed, insulin likely needed"
                elif v > 7.8: lv, r = "MEDIUM", f"GCT {v} mmol/L — GDM, dietary management required"
                else:         lv, r = "LOW",    f"GCT {v} mmol/L — within target"
                out.append(RiskScore("Gestational Glucose (GCT)", "Prenatal / GDM",
                                     lv, f"{v}", "mmol/L", r))
            break

    for k in ("2-hour ogtt — 2h", "ogtt 2h"):
        lab = labs.get(k)
        if lab:
            v = _num(lab.get("value"))
            if v is not None:
                if v >= 11.1:  lv, r = "HIGH",   f"OGTT 2h {v} mmol/L — severe GDM"
                elif v >= 8.5: lv, r = "MEDIUM", f"OGTT 2h {v} mmol/L — GDM threshold exceeded"
                else:          lv, r = "LOW",    f"OGTT 2h {v} mmol/L — within target"
                out.append(RiskScore("OGTT 2-Hour — GDM Severity", "Prenatal / GDM",
                                     lv, f"{v}", "mmol/L", r))
            break

    sbp, dbp = _bp(patient)
    if sbp is not None and _has_condition(patient, "pregnancy", "prenatal", "gestational"):
        if sbp >= 140 or (dbp or 0) >= 90:
            lv, r = "HIGH",   f"BP {sbp}/{dbp} — pre-eclampsia threshold reached"
        elif sbp >= 130:
            lv, r = "MEDIUM", f"BP {sbp}/{dbp} — borderline, frequent monitoring"
        else:
            lv, r = "LOW",    f"BP {sbp}/{dbp} — normal in pregnancy"
        out.append(RiskScore("Blood Pressure (Pregnancy)", "Prenatal / Pre-eclampsia",
                             lv, f"{sbp}/{dbp}", "mmHg", r))

    return out


def _oncology(patient: dict, labs: dict) -> List[RiskScore]:
    out = []

    for k in ("ca 15-3 (tumour marker)", "ca 15-3", "ca15-3"):
        lab = labs.get(k)
        if lab:
            v = _num(lab.get("value"))
            if v is not None:
                if v > 35:   lv, r = "HIGH",   f"CA 15-3 {v} U/mL — elevated, possible recurrence"
                elif v > 25: lv, r = "MEDIUM", f"CA 15-3 {v} U/mL — borderline, trend closely"
                else:        lv, r = "LOW",    f"CA 15-3 {v} U/mL — normal surveillance"
                out.append(RiskScore("CA 15-3 — Breast Cancer Marker",
                                     "Oncology Surveillance", lv, f"{v}", "U/mL", r))
            break

    lab = labs.get("cea")
    if lab:
        v = _num(lab.get("value"))
        if v is not None:
            if v > 10:  lv, r = "HIGH",   f"CEA {v} ng/mL — significantly elevated"
            elif v > 5: lv, r = "MEDIUM", f"CEA {v} ng/mL — borderline"
            else:       lv, r = "LOW",    f"CEA {v} ng/mL — normal"
            out.append(RiskScore("CEA — Tumour Marker", "Oncology Surveillance",
                                 lv, f"{v}", "ng/mL", r))

    return out


def _pain(patient: dict, labs: dict) -> List[RiskScore]:
    out = []
    ca = patient.get("clinical_assessment", {})

    for label, field in (("Pain at Rest", "pain_at_rest"),
                         ("Pain with Activity", "pain_with_activity")):
        raw = ca.get(field, "")
        if raw:
            v = _num(raw)
            if v is not None:
                if v >= 7:   lv, r = "HIGH",   f"{label} {int(v)}/10 — severe, functional impairment"
                elif v >= 4: lv, r = "MEDIUM", f"{label} {int(v)}/10 — moderate"
                else:        lv, r = "LOW",    f"{label} {int(v)}/10 — mild"
                out.append(RiskScore(f"{label} (VAS)", "Musculoskeletal / Pain",
                                     lv, f"{int(v)}/10", "/10", r))

    return out


def _anemia(patient: dict, labs: dict) -> List[RiskScore]:
    for k in ("cbc — hemoglobin", "hemoglobin", "haemoglobin"):
        lab = labs.get(k)
        if lab:
            v = _num(lab.get("value"))
            if v is not None:
                female = patient.get("gender", "").lower() in ("female", "f")
                norm = 120 if female else 135
                if v < 100:    lv, r = "HIGH",   f"Hgb {v} g/L — severe anaemia"
                elif v < norm: lv, r = "MEDIUM", f"Hgb {v} g/L — anaemia (normal >{norm})"
                else:          lv, r = "LOW",    f"Hgb {v} g/L — normal"
                return [RiskScore("Hemoglobin — Anaemia Screen",
                                  "Hematology", lv, f"{v}", "g/L", r)]
    return []


def _infection(patient: dict, labs: dict) -> List[RiskScore]:
    out = []

    lab = labs.get("hiv viral load")
    if lab:
        val_str = str(lab.get("value", "")).lower()
        if "undetectable" in val_str or "< 20" in val_str:
            lv, r = "LOW", "HIV viral load undetectable — well controlled on ART"
        else:
            lv, r = "HIGH", f"HIV viral load {lab.get('value')} — not suppressed"
        out.append(RiskScore("HIV Viral Load", "Infectious Disease",
                             lv, lab.get("value", "?"), "copies/mL", r))

    lab = labs.get("cd4 count")
    if lab:
        v = _num(lab.get("value"))
        if v is not None:
            if v < 200:   lv, r = "HIGH",   f"CD4 {int(v)} — AIDS-defining immunodeficiency"
            elif v < 500: lv, r = "MEDIUM", f"CD4 {int(v)} — moderate immune suppression"
            else:         lv, r = "LOW",    f"CD4 {int(v)} — good immune reconstitution"
            out.append(RiskScore("CD4 Count", "Infectious Disease",
                                 lv, f"{int(v)}", "cells/µL", r))

    return out


# ── Master public API ─────────────────────────────────────────────────────────

def score_patient(patient: dict) -> List[RiskScore]:
    """Return all applicable risk scores for a patient, deduped by name."""
    labs = _labs(patient)
    raw = (
        _cardiac(patient, labs)
        + _diabetes(patient, labs)
        + _kidney(patient, labs)
        + _mental_health(patient, labs)
        + _respiratory(patient, labs)
        + _rheumatology(patient, labs)
        + _anaphylaxis(patient, labs)
        + _prenatal(patient, labs)
        + _oncology(patient, labs)
        + _pain(patient, labs)
        + _anemia(patient, labs)
        + _infection(patient, labs)
    )
    # Keep highest level per name
    seen: dict[str, RiskScore] = {}
    for s in raw:
        if s.name not in seen or LEVEL_ORDER[s.level] > LEVEL_ORDER[seen[s.name].level]:
            seen[s.name] = s
    return list(seen.values())


def top_risk_level(patient: dict) -> str:
    scores = score_patient(patient)
    if any(s.level == "HIGH"   for s in scores): return "HIGH"
    if any(s.level == "MEDIUM" for s in scores): return "MEDIUM"
    return "LOW"


def appointment_context(patient: dict) -> dict:
    """
    Returns a compact summary for use in the scheduler:
    top risk level, top 3 scores, appointment type/color/badge derived from conditions.
    """
    scores  = score_patient(patient)
    sorted_s = sorted(scores, key=lambda s: -LEVEL_ORDER[s.level])
    conds   = patient.get("conditions", [])
    cond_text = " ".join(c.get("display", "").lower() for c in conds)

    # derive appointment color
    if "pregnancy" in cond_text or "gestational" in cond_text or "prenatal" in cond_text:
        color, badge = "pink",   "Prenatal"
    elif "kidney" in cond_text or "renal" in cond_text:
        color, badge = "red",    "CKD"
    elif "depression" in cond_text or "anxiety" in cond_text or "mental" in cond_text:
        color, badge = "purple", "MH"
    elif "copd" in cond_text or "pulmonary" in cond_text:
        color, badge = "orange", "COPD"
    elif "asthma" in cond_text or "allerg" in cond_text:
        color, badge = "blue",   "Asthma"
    elif "rheumatoid" in cond_text or "arthritis" in cond_text:
        color, badge = "blue",   "RA"
    elif "cancer" in cond_text or "breast" in cond_text:
        color, badge = "green",  "Oncology"
    elif "opioid" in cond_text or "substance" in cond_text:
        color, badge = "teal",   "OAT"
    elif "diabetes" in cond_text:
        color, badge = "blue",   "Diabetes"
    elif "sprain" in cond_text or "back pain" in cond_text or "injury" in cond_text:
        color, badge = "orange", "WSIB"
    elif "hypertension" in cond_text:
        color, badge = "red",    "HTN"
    else:
        color, badge = "blue",   "Clinic"

    # derive appointment type from top risk
    if sorted_s:
        top = sorted_s[0]
        appt_type = f"{top.category} review — {top.name.split('—')[0].strip().rstrip()}"
    elif conds:
        appt_type = conds[0].get("display", "Clinical review")
    else:
        appt_type = "Clinical review"

    # duration from risk level
    trl = top_risk_level(patient)
    duration = 30 if trl == "HIGH" else 20 if trl == "MEDIUM" else 15

    return {
        "top_risk_level": trl,
        "color":          color,
        "badge":          badge,
        "appt_type":      appt_type,
        "duration":       duration,
        "scores":         [s.to_dict() for s in sorted_s[:3]],
        "high_count":     sum(1 for s in scores if s.level == "HIGH"),
        "medium_count":   sum(1 for s in scores if s.level == "MEDIUM"),
    }
