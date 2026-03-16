import os
import json
import time
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()


def _secret(key: str, default: str = "") -> str:
    try:
        import streamlit as st
        return st.secrets[key]
    except Exception:
        return os.getenv(key, default)


LANGDOCK_API_KEY = _secret("LANGDOCK_API_KEY")
LANGDOCK_AGENT_ID = _secret("LANGDOCK_AGENT_ID")
LANGDOCK_URL = "https://api.langdock.com/agent/v1/chat/completions"
ANTHROPIC_API_KEY = _secret("ANTHROPIC_API_KEY")
APIFY_API_TOKEN = _secret("APIFY_API_TOKEN")
APIFY_TIKTOK_ACTOR = "clockworks~tiktok-scraper"


def send_to_visual_director(entry: dict, profile: dict = None) -> dict:
    """Schickt einen Content-Eintrag an Langdock und bekommt strukturiertes Briefing zurück."""

    content_json = json.dumps(entry, ensure_ascii=False, indent=2)

    ci_context = ""
    if profile:
        colors_str = ", ".join([f"{c['name']}: {c['hex']}" for c in profile.get("colors", [])])
        ci_context = f"""
WICHTIG – Corporate Identity des Kunden:
- Firma: {profile.get('name', '')}
- Branche: {profile.get('industry', '')}
- Slogan: {profile.get('slogan', '')}
- Zielgruppe: {profile.get('target_audience', '')}
- Tonalität: {profile.get('tone', '')}
- Markenwerte: {profile.get('values', '')}
- Markenfarben: {colors_str}
- Schrift: {profile.get('font', '')}
- Hinweise: {profile.get('notes', '')}

Nutze die Markenfarben als Basis für die Farbpalette und passe Mood, Tonalität und Stil an die CI an.
"""

    prompt = f"""Hier ist ein Content-Plan-Eintrag.
Erstelle das visuelle Briefing und gib es als valides JSON zurück – kein Text davor oder danach, nur JSON.
{ci_context}

Das JSON muss exakt diese Struktur haben:
{{
  "mood": "Ein Satz der die Gesamtästhetik beschreibt",
  "colors": [
    {{"name": "Primär", "hex": "#XXXXXX"}},
    {{"name": "Sekundär", "hex": "#XXXXXX"}},
    {{"name": "Akzent", "hex": "#XXXXXX"}}
  ],
  "light": "Beschreibung des Licht-Setups",
  "reference_creator": "Name eines bekannten Creators oder Brands als Referenz",
  "shots": [
    {{"number": 1, "description": "Kamerawinkel, Motiv, Dauer"}},
    {{"number": 2, "description": "..."}},
    {{"number": 3, "description": "..."}}
  ],
  "text_overlay": {{
    "style": "Bold / Handwritten / Clean Sans-Serif",
    "position": "Oben / Mitte / Unten",
    "text": "Exakter Wortlaut des Overlays",
    "color": "#XXXXXX"
  }},
  "pacing": "schnell / mittel / langsam",
  "transition": "Hard Cut / Zoom / Whip Pan / None",
  "music_mood": "energetisch / emotional / ruhig / hype",
  "music_example": "Beispiel Sound-Typ oder Genre",
  "thumbnail_frame": "Beschreibung welcher Frame als Thumbnail",
  "duration_seconds": 30,
  "equipment": "Handy reicht / Stativ nötig / 2. Person nötig",
  "effort": "Niedrig / Mittel / Hoch",
  "production_notes": "Wichtigste Hinweise für das Filmteam in 2 Sätzen"
}}

Content-Eintrag:
{content_json}"""

    # Try Langdock first, fall back to Claude
    for api_call, label in [(_call_langdock, "Langdock"), (_call_claude, "Claude")]:
        if label == "Langdock" and not (LANGDOCK_API_KEY and LANGDOCK_AGENT_ID):
            continue
        if label == "Claude" and not ANTHROPIC_API_KEY:
            continue
        try:
            raw = api_call(prompt)
            text = _extract_json_text(raw)
            return json.loads(text)
        except Exception as e:
            print(f"  {label} Fehler: {e}")

    return {
        "mood": "API nicht erreichbar",
        "colors": [{"name": "Primär", "hex": "#1a1a2e"}],
        "shots": [{"number": 1, "description": "Bitte erneut versuchen"}],
        "effort": "Mittel",
        "production_notes": "Konnte nicht generiert werden"
    }


def search_reference_videos(topic: str, max_results: int = 3) -> list:
    """Sucht auf TikTok nach Referenzvideos zum Thema via Apify."""
    if not APIFY_API_TOKEN:
        return []

    run_url = f"https://api.apify.com/v2/acts/{APIFY_TIKTOK_ACTOR}/runs?token={APIFY_API_TOKEN}&waitForFinish=90"
    payload = {
        "searchQueries": [topic],
        "resultsPerPage": max_results,
        "searchSection": "/video"
    }

    try:
        run_resp = requests.post(run_url, json=payload)
        run_resp.raise_for_status()
        run_data = run_resp.json()
        dataset_id = run_data["data"]["defaultDatasetId"]

        items_url = f"https://api.apify.com/v2/datasets/{dataset_id}/items?token={APIFY_API_TOKEN}&limit={max_results}"
        items_resp = requests.get(items_url)
        items_resp.raise_for_status()
        items = items_resp.json()

        references = []
        for item in items[:max_results]:
            url = item.get("webVideoUrl", "")
            if not url:
                continue
            references.append({
                "url": url,
                "description": (item.get("text", "") or "")[:120],
                "author": item.get("authorMeta", {}).get("name", item.get("author", "?")),
                "views": item.get("playCount", 0),
                "likes": item.get("diggCount", 0),
                "platform": "TikTok"
            })
        return references
    except Exception as e:
        print(f"  ⚠️ Referenzsuche fehlgeschlagen: {e}")
        return []


def load_profile(profile_slug: str) -> dict:
    """Lädt ein Kundenprofil aus data/profiles/."""
    path = f"data/profiles/{profile_slug}.json"
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def generate_raw_content_plan(profile: dict, days: int = 7, posts_per_day: int = 1, notes: str = "") -> list:
    """Generates a raw content plan via Langdock based on the client profile."""

    colors_str = ", ".join([f"{c['name']}: {c['hex']}" for c in profile.get("colors", [])])
    total_posts = days * posts_per_day

    notes_section = ""
    if notes:
        notes_section = f"\nZusaetzliche Hinweise:\n{notes}\n"

    prompt = f"""Erstelle einen Content-Plan mit genau {total_posts} Posts fuer {days} Tage ({posts_per_day} Post(s) pro Tag).

Kundenprofil:
- Firma: {profile.get('name', '')}
- Branche: {profile.get('industry', '')}
- Slogan: {profile.get('slogan', '')}
- Zielgruppe: {profile.get('target_audience', '')}
- Tonalitaet: {profile.get('tone', '')}
- Markenwerte: {profile.get('values', '')}
- Markenfarben: {colors_str}
- Sprache: {profile.get('language', 'Deutsch')}
- Hinweise: {profile.get('notes', '')}
{notes_section}

Gib das Ergebnis als valides JSON-Array zurueck – kein Text davor oder danach, nur JSON.

Jeder Eintrag MUSS exakt diese Keys haben:
[
  {{
    "week": 1,
    "week_theme": "Thema der Woche",
    "day": "Montag",
    "topic": "Konkretes Thema des Posts",
    "platform": ["TikTok", "Instagram Reel"],
    "format": "Day-in-the-Life / Listicle / Testimonial / Tutorial / etc.",
    "hook": "Aufmerksamkeitsstarker erster Satz",
    "caption": "Fertige Caption mit Hashtags",
    "best_time": "12:00",
    "target_audience": "{profile.get('target_audience', 'Allgemein')}"
  }}
]

WICHTIG:
- Jeder Post braucht einen einzigartigen, kreativen Hook
- Captions muessen ready-to-post sein mit passenden Hashtags
- Variiere die Formate (nicht nur ein Typ)
- Beruecksichtige die Tonalitaet und Zielgruppe
- Tage: Montag bis Sonntag, dann wieder Montag etc.
- Verteile Posts gleichmaessig auf die Tage"""

    # Try each API — if response can't be parsed, try the next one
    errors = []

    # 1. Try Langdock
    if LANGDOCK_API_KEY and LANGDOCK_AGENT_ID:
        try:
            raw = _call_langdock(prompt)
            parsed = _try_parse_json_plan(raw)
            if parsed:
                return parsed
            errors.append("Langdock: Antwort kam, aber JSON ungueltig")
        except Exception as e:
            errors.append(f"Langdock: {e}")

    # 2. Try Claude (always if Langdock failed or returned bad JSON)
    if ANTHROPIC_API_KEY:
        try:
            print(f"  Wechsle zu Claude API...")
            raw = _call_claude(prompt)
            parsed = _try_parse_json_plan(raw)
            if parsed:
                return parsed
            errors.append("Claude: Antwort kam, aber JSON ungueltig")
        except Exception as e:
            errors.append(f"Claude: {e}")

    if not LANGDOCK_API_KEY and not ANTHROPIC_API_KEY:
        raise ValueError("Kein API-Key konfiguriert (weder LANGDOCK noch ANTHROPIC_API_KEY)")

    error_detail = " | ".join(errors)
    raise ValueError(f"Content-Plan fehlgeschlagen: {error_detail}")


def _try_parse_json_plan(raw_text: str) -> list:
    """Try to parse a JSON plan from raw API response. Returns list or None."""
    if not raw_text or not raw_text.strip():
        return None

    text = _extract_json_text(raw_text)

    # Try direct parse
    try:
        result = json.loads(text)
        if isinstance(result, list) and len(result) > 0:
            return result
    except json.JSONDecodeError:
        pass

    # Try repair truncated JSON
    repaired = _repair_truncated_json_array(text)
    if repaired:
        return repaired

    return None


def _extract_json_text(raw_text: str) -> str:
    """Extract JSON from markdown code blocks and fix common issues."""
    text = raw_text.strip()
    if "```" in text:
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        if "```" in text:
            text = text.split("```")[0]
    text = text.strip()

    # Fix unescaped newlines inside JSON string values
    # This handles cases where Claude puts actual \n in captions
    text = _fix_json_newlines(text)
    return text


def _fix_json_newlines(text: str) -> str:
    """Replace raw newlines inside JSON string values with \\n."""
    result = []
    in_string = False
    escape = False
    for ch in text:
        if escape:
            result.append(ch)
            escape = False
            continue
        if ch == '\\':
            result.append(ch)
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            result.append(ch)
            continue
        if in_string and ch == '\n':
            result.append('\\n')
            continue
        result.append(ch)
    return ''.join(result)


def _repair_truncated_json_array(text: str) -> list:
    """Try to salvage a truncated JSON array by finding the last complete object."""
    text = text.strip()
    if not text.startswith("["):
        return []

    # Find positions of all complete objects (closing "}")
    last_complete = -1
    depth = 0
    in_string = False
    escape = False

    for i, ch in enumerate(text):
        if escape:
            escape = False
            continue
        if ch == '\\':
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                last_complete = i

    if last_complete <= 0:
        return []

    # Cut after last complete object and close the array
    truncated = text[:last_complete + 1].rstrip().rstrip(",")
    truncated = truncated + "\n]"

    try:
        result = json.loads(truncated)
        if isinstance(result, list) and len(result) > 0:
            print(f"  JSON repariert: {len(result)} Posts aus abgeschnittener Antwort gerettet")
            return result
    except json.JSONDecodeError:
        pass

    return []


def _call_langdock(prompt: str) -> str:
    """Call Langdock API. Returns raw text response or raises on failure."""
    headers = {
        "Authorization": f"Bearer {LANGDOCK_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "agentId": LANGDOCK_AGENT_ID,
        "messages": [{"id": "msg-1", "role": "user", "parts": [{"type": "text", "text": prompt}]}],
        "stream": False
    }

    response = None
    for attempt in range(3):
        response = requests.post(LANGDOCK_URL, headers=headers, json=payload, timeout=120)
        if response.status_code == 429:
            wait = 15 * (attempt + 1)
            print(f"  Rate Limit – warte {wait}s...")
            time.sleep(wait)
            continue
        response.raise_for_status()
        break
    else:
        raise RuntimeError(f"Langdock: nach 3 Versuchen fehlgeschlagen (letzter Status: {response.status_code if response else 'keine Antwort'})")

    data = response.json()
    raw_text = ""
    for msg in data.get("result", []):
        if msg.get("role") == "assistant":
            for part in msg.get("parts", []):
                if isinstance(part, dict) and part.get("type") == "text":
                    raw_text = part.get("text", "")
                elif isinstance(part, str):
                    raw_text = part
            if not raw_text:
                content = msg.get("content", [])
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        raw_text = block.get("text", "")
                    elif isinstance(block, str):
                        raw_text = block

    if not raw_text:
        raise RuntimeError(f"Langdock: leere Antwort erhalten")
    return raw_text


def _call_claude(prompt: str) -> str:
    """Call Anthropic Claude API as fallback. Returns raw text response."""
    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    with client.messages.stream(
        model="claude-sonnet-4-6",
        max_tokens=16384,
        messages=[{"role": "user", "content": prompt}]
    ) as stream:
        response = stream.get_final_message()

    # If output was truncated, the JSON will be incomplete
    if response.stop_reason == "max_tokens":
        raise RuntimeError("Claude: Antwort wurde abgeschnitten (max_tokens erreicht)")

    for block in response.content:
        if block.type == "text":
            text = block.text.strip()
            if text:
                return text

    raise RuntimeError("Claude: leere Antwort erhalten")


def run_pipeline_from_ui(profile_slug: str, days: int = 7, posts_per_day: int = 1, notes: str = "") -> str:
    """Generates content plan from UI: creates raw plan, enriches it, saves output."""

    profile = load_profile(profile_slug)
    if not profile:
        raise ValueError(f"Profil '{profile_slug}' nicht gefunden.")

    client_name = profile.get("name", profile_slug)
    print(f"\n[1/3] Content-Plan generieren fuer {client_name}...")

    raw_plan = generate_raw_content_plan(profile, days, posts_per_day, notes)
    if not raw_plan:
        raise ValueError("Content-Plan konnte nicht generiert werden.")
    print(f"  {len(raw_plan)} Posts generiert")

    print(f"\n[2/3] Visual Briefings + Referenzen erstellen...")
    enriched_plan = []
    for i, entry in enumerate(raw_plan):
        print(f"  [{i+1}/{len(raw_plan)}] {entry.get('day', '')} – {entry.get('topic', '')}...")
        visual = send_to_visual_director(entry, profile=profile)
        references = search_reference_videos(entry.get("topic", ""))
        enriched_plan.append({**entry, "visual_briefing": visual, "reference_videos": references})

    print(f"\n[3/3] Speichern...")
    os.makedirs("outputs", exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    output_path = f"outputs/{profile_slug}_{timestamp}.json"

    result = {
        "client": client_name,
        "generated_at": timestamp,
        "profile": profile_slug,
        "plan": enriched_plan
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    with open("outputs/latest.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\nPipeline fertig → {output_path}")
    return output_path


def run_pipeline(input_json_path: str, client_name: str, profile_slug: str = None):
    """Hauptfunktion: Liest Raw JSON, enriched mit Langdock, speichert Output."""

    with open(input_json_path, "r", encoding="utf-8") as f:
        content_plan = json.load(f)

    # Profil laden falls angegeben
    profile = {}
    if profile_slug:
        profile = load_profile(profile_slug)
        if profile:
            print(f"👤 Profil geladen: {profile.get('name', profile_slug)}")
        else:
            print(f"⚠️ Profil '{profile_slug}' nicht gefunden, fahre ohne fort.")

    enriched_plan = []

    for i, entry in enumerate(content_plan):
        print(f"[{i+1}/{len(content_plan)}] {entry.get('day', '')} – {entry.get('topic', '')}...")
        visual = send_to_visual_director(entry, profile=profile)
        print(f"  🔍 Suche Referenzvideos...")
        references = search_reference_videos(entry.get("topic", ""))
        enriched_plan.append({**entry, "visual_briefing": visual, "reference_videos": references})
        print(f"  ✅ Fertig ({len(references)} Referenzen gefunden)")

    # Speichern
    os.makedirs("outputs", exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    output_path = f"outputs/{client_name}_{timestamp}.json"

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(enriched_plan, f, ensure_ascii=False, indent=2)

    # Auch als "latest" speichern damit Streamlit immer aktuellsten Plan zeigt
    with open("outputs/latest.json", "w", encoding="utf-8") as f:
        json.dump({
            "client": client_name,
            "generated_at": timestamp,
            "profile": profile_slug or "",
            "plan": enriched_plan
        }, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Pipeline fertig → {output_path}")
    print("🚀 Streamlit zeigt jetzt den aktuellen Plan an.")
    return output_path


if __name__ == "__main__":
    import sys
    input_path = sys.argv[1] if len(sys.argv) > 1 else "data/content_plan_raw.json"
    client = sys.argv[2] if len(sys.argv) > 2 else "Kunde"
    profile = sys.argv[3] if len(sys.argv) > 3 else None
    run_pipeline(input_path, client, profile)
