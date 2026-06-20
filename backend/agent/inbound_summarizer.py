import json
import os
import anthropic

_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
MODEL = "claude-haiku-4-5-20251001"

_PROMPT = """You are a Canadian family physician's AI assistant reviewing an inbound specialist report.

SPECIALIST REPORT:
{report_text}

Summarize this for the primary care physician. Return ONLY valid JSON — no markdown, no explanation:
{{
  "summary": "One concise paragraph (3-5 sentences) for a busy GP: specialist's overall impression, key clinical findings, any medication or management changes made, and the single most important next step.",
  "key_changes": ["each specific clinical change the specialist made — medication added/stopped/changed, new diagnosis confirmed, procedure performed, further referral placed"],
  "followup_actions": ["each concrete action the GP must take — lab orders, follow-up appointment timing, patient instructions, prescriptions to action"],
  "missing_info": ["each piece of information typically expected in this type of specialist report that is absent, ambiguous, or unclear"]
}}"""


def summarize_inbound_note(text: str) -> dict:
    prompt = _PROMPT.format(report_text=text[:8000])
    msg = _client.messages.create(
        model=MODEL,
        max_tokens=1024,
        temperature=0.05,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = msg.content[0].text.strip()
    if "```json" in raw:
        raw = raw.split("```json")[1].split("```")[0].strip()
    elif "```" in raw:
        raw = raw.split("```")[1].split("```")[0].strip()
    start = raw.find("{")
    end   = raw.rfind("}") + 1
    return json.loads(raw[start:end])
