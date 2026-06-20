"""
Combined form analysis + field filling in a single Claude API call.
One round-trip instead of two — roughly 2x faster than the split approach.
"""
import json
import os
import anthropic
from dataclasses import dataclass

from ocr.form_analyzer import FormSchema, FormField
from agent.field_mapper import FilledField, CONFIDENCE_MISSING

_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
MODEL = "claude-haiku-4-5-20251001"

_PROMPT = """You are a medical office assistant helping a Canadian primary care physician complete a form.

PATIENT RECORD:
{patient_context}

FORM TEXT (OCR-extracted from uploaded document):
{ocr_text}

TASK: Read the form, identify every fillable field, then fill each field using ONLY the patient record above.

Return ONLY valid JSON — no explanation, no markdown fences, no trailing text:
{{
  "form_type": "Full name of the form",
  "issuer": "Organization that issues this form",
  "purpose": "One sentence: what this form is used for",
  "fields": [
    {{
      "key": "snake_case_identifier",
      "label": "Exact label text from the form",
      "value": "Value from patient record, or empty string if unknown",
      "confidence": "HIGH|MEDIUM|LOW|MISSING",
      "source": "Brief source (max 8 words)",
      "note": "Brief physician note (max 10 words, empty if none)"
    }}
  ]
}}

Rules:
- Include ALL fillable fields: patient info, dates, diagnoses, medications, checkboxes, billing, signatures
- Never invent values — use only what is in the patient record
- For dates: use DD/MM/YYYY format for WSIB forms, YYYY-MM-DD otherwise
- Always mark signature fields as MISSING
- For physician fields use the physician block from the patient record
- For SIN use the sin field from the patient record if present
- Keep source and note SHORT — this reduces response size
- Return valid JSON only — the response must be complete and parseable"""


def analyze_and_fill(ocr_text: str, patient_context: str) -> tuple[FormSchema, list[FilledField]]:
    """
    Single Claude call that understands the form AND fills all fields.
    Returns (FormSchema, list[FilledField]).
    """
    prompt = _PROMPT.format(
        patient_context=patient_context,
        ocr_text=ocr_text[:6000],
    )

    message = _client.messages.create(
        model=MODEL,
        max_tokens=8096,       # raised from 4096 — large forms need more room
        temperature=0.05,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text
    return _parse_response(raw)


def _parse_response(text: str) -> tuple[FormSchema, list[FilledField]]:
    clean = text.strip()
    if "```json" in clean:
        clean = clean.split("```json")[1].split("```")[0].strip()
    elif "```" in clean:
        clean = clean.split("```")[1].split("```")[0].strip()

    start = clean.find("{")
    if start == -1:
        raise ValueError(f"No JSON in Claude response: {text[:300]}")

    end = clean.rfind("}") + 1
    json_str = clean[start:end]

    # Primary parse attempt
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        # Fallback: response was likely truncated — recover complete field objects
        data = _recover_truncated(json_str)

    form_fields = []
    filled      = []

    for f in data.get("fields", []):
        key = f.get("key", "")
        form_fields.append(FormField(
            key=key,
            label=f.get("label", ""),
            field_type="text",
            required=True,
            what_it_needs="",
            fhir_hint="",
            options=[],
        ))
        filled.append(FilledField(
            key=key,
            label=f.get("label", ""),
            value=f.get("value", ""),
            confidence=f.get("confidence", CONFIDENCE_MISSING),
            source=f.get("source", ""),
            note=f.get("note", ""),
        ))

    schema = FormSchema(
        form_type=data.get("form_type", "Unknown Form"),
        issuer=data.get("issuer", ""),
        purpose=data.get("purpose", ""),
        fields=form_fields,
    )

    return schema, filled


def _recover_truncated(text: str) -> dict:
    """
    Recover as many complete field objects as possible from a truncated JSON response.
    Claude sometimes gets cut off mid-field on very large forms.
    """
    # Parse outer envelope properties (form_type, issuer, purpose)
    outer = {"form_type": "Unknown Form", "issuer": "", "purpose": "", "fields": []}
    for key in ("form_type", "issuer", "purpose"):
        marker = f'"{key}"'
        idx = text.find(marker)
        if idx != -1:
            val_start = text.find('"', idx + len(marker) + 1)
            val_end   = text.find('"', val_start + 1)
            if val_start != -1 and val_end != -1:
                outer[key] = text[val_start+1:val_end]

    # Find the fields array
    fields_idx = text.find('"fields"')
    if fields_idx == -1:
        return outer

    bracket = text.find('[', fields_idx)
    if bracket == -1:
        return outer

    # Walk character by character, extracting complete {...} objects
    complete = []
    depth = 0
    obj_start = None

    for pos, ch in enumerate(text[bracket + 1:], start=bracket + 1):
        if ch == '{':
            if depth == 0:
                obj_start = pos
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0 and obj_start is not None:
                try:
                    obj = json.loads(text[obj_start:pos + 1])
                    complete.append(obj)
                except json.JSONDecodeError:
                    pass
                obj_start = None

    outer["fields"] = complete
    return outer
