"""
Form analyzer using Claude Haiku via Anthropic API.
Sends OCR-extracted text and returns a structured list of form fields
with their intent and FHIR mapping hints.
"""
import json
import os
import anthropic
from dataclasses import dataclass

_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
MODEL = "claude-haiku-4-5-20251001"


@dataclass
class FormField:
    key: str            # snake_case identifier
    label: str          # original label from the form
    field_type: str     # text | date | checkbox | number | signature
    required: bool
    what_it_needs: str  # plain English description of what data fills this
    fhir_hint: str      # e.g. "Patient.name", "Condition.onsetDate"
    options: list[str]  # for checkboxes/dropdowns


@dataclass
class FormSchema:
    form_type: str      # e.g. "WSIB Form 6 - Physician Report"
    issuer: str         # e.g. "Workplace Safety and Insurance Board"
    purpose: str        # one-sentence description
    fields: list[FormField]


EXTRACTION_PROMPT = """You are analyzing a medical/administrative form that a primary care physician needs to complete.

I will provide you with:
1. The text content extracted from the form (via OCR)
2. An image of the form

Your task is to identify ALL fields that need to be filled in by the physician and return a structured JSON object.

For each fillable field, extract:
- key: snake_case identifier (e.g. patient_name, date_of_injury)
- label: the exact label text from the form
- field_type: one of "text", "date", "checkbox", "number", "textarea", "signature"
- required: true if marked required or logically required
- what_it_needs: plain English description of what patient data fills this field
- fhir_hint: the most relevant FHIR R4 resource path (e.g. "Patient.name.text", "Condition.onsetDateTime", "MedicationRequest.medicationCodeableConcept")
- options: array of choices if it's a checkbox/radio/dropdown, else empty array

Also identify:
- form_type: the name and number of this form
- issuer: the organization that issued this form
- purpose: one sentence on what this form is for

Return ONLY valid JSON in this exact structure:
{
  "form_type": "...",
  "issuer": "...",
  "purpose": "...",
  "fields": [
    {
      "key": "...",
      "label": "...",
      "field_type": "...",
      "required": true,
      "what_it_needs": "...",
      "fhir_hint": "...",
      "options": []
    }
  ]
}

Extracted OCR text:
{ocr_text}
"""


def analyze_form(ocr_text: str, page_image_b64: str) -> FormSchema:
    """
    Sends OCR-extracted form text to Claude Haiku to identify and understand all form fields.
    """
    prompt = EXTRACTION_PROMPT.replace("{ocr_text}", ocr_text[:6000])

    message = _client.messages.create(
        model=MODEL,
        max_tokens=2048,
        temperature=0.1,
        messages=[{"role": "user", "content": prompt}],
    )

    generated = message.content[0].text
    return _parse_form_schema(generated)


def _parse_form_schema(text: str) -> FormSchema:
    # Strip any markdown fences
    clean = text.strip()
    if "```json" in clean:
        clean = clean.split("```json")[1].split("```")[0].strip()
    elif "```" in clean:
        clean = clean.split("```")[1].split("```")[0].strip()

    # Find first { to last }
    start = clean.find("{")
    end = clean.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError(f"No JSON found in model response: {text[:200]}")

    data = json.loads(clean[start:end])

    fields = []
    for f in data.get("fields", []):
        fields.append(FormField(
            key=f.get("key", ""),
            label=f.get("label", ""),
            field_type=f.get("field_type", "text"),
            required=bool(f.get("required", False)),
            what_it_needs=f.get("what_it_needs", ""),
            fhir_hint=f.get("fhir_hint", ""),
            options=f.get("options", []),
        ))

    return FormSchema(
        form_type=data.get("form_type", "Unknown Form"),
        issuer=data.get("issuer", ""),
        purpose=data.get("purpose", ""),
        fields=fields,
    )
