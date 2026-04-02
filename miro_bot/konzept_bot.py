"""
Konzept Bot — generates concepts via Langdock (Merlin) and places them on Miro boards.
"""
import json
import re
import requests
import os
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


CONCEPT_TYPES = {
    "grobkonzept": {
        "label": "Grobkonzept",
        "description": "Überblick mit strategischen Eckpfeilern, Zielen und groben Maßnahmen",
        "sections_hint": "3-5 Abschnitte mit jeweils 2-4 strategischen Punkten. Fokus auf das große Bild.",
    },
    "feinkonzept": {
        "label": "Feinkonzept",
        "description": "Detailliertes Konzept mit konkreten Maßnahmen, Timelines und Verantwortlichkeiten",
        "sections_hint": "5-8 Abschnitte mit jeweils 3-6 detaillierten, umsetzbaren Punkten. Konkret und spezifisch.",
    },
    "reels": {
        "label": "Reels-Konzept",
        "description": "Konzept für Social Media Reels/Kurzvideos mit Hooks, Szenen und CTAs",
        "sections_hint": "4-6 Abschnitte (z.B. Hook-Ideen, Szenenaufbau, Storytelling, CTAs, Musik/Sound). Jeder Punkt beschreibt eine konkrete Reel-Idee oder Szene.",
    },
}


def generate_concept(thema: str, concept_type: str = "grobkonzept",
                     profile: dict = None, kontext: str = "",
                     file_text: str = "") -> dict:
    """Ask Merlin (Langdock) to generate a structured concept.

    Args:
        thema: Main topic/brief
        concept_type: One of CONCEPT_TYPES keys
        profile: Customer profile dict (optional)
        kontext: Additional context text (optional)
        file_text: Extracted text from uploaded files (optional)

    Returns dict with: title, sections (list of {heading, points}).
    """
    if not LANGDOCK_API_KEY or not LANGDOCK_AGENT_ID:
        raise RuntimeError("LANGDOCK_API_KEY oder LANGDOCK_AGENT_ID nicht konfiguriert")

    ctype = CONCEPT_TYPES.get(concept_type, CONCEPT_TYPES["grobkonzept"])

    # Build profile context
    profile_block = ""
    if profile:
        parts = []
        if profile.get("name"):
            parts.append(f"Kunde: {profile['name']}")
        if profile.get("industry"):
            parts.append(f"Branche: {profile['industry']}")
        if profile.get("target_audience"):
            parts.append(f"Zielgruppe: {profile['target_audience']}")
        if profile.get("tone"):
            parts.append(f"Tonalität: {profile['tone']}")
        if profile.get("values"):
            parts.append(f"Werte: {profile['values']}")
        if profile.get("notes"):
            parts.append(f"Hinweise: {profile['notes']}")
        if parts:
            profile_block = "Kundenprofil:\n" + "\n".join(parts)

    prompt = f"""Erstelle ein {ctype['label']} zum Thema: "{thema}"

Typ: {ctype['description']}

{profile_block}

{f"Zusätzlicher Kontext: {kontext}" if kontext else ""}

{f"Dokument-Inhalt (z.B. Stellenanzeige, Briefing):\n{file_text[:6000]}" if file_text else ""}

WICHTIGE REGELN für die Texte:
- Schreibe natürlich und menschlich, KEINE AI-Sprache
- KEINE Gedankenstriche am Satzanfang
- KEINE Aufzählungszeichen oder Bulletpoints im Text
- Formuliere in ganzen, kurzen Sätzen
- Direkt, klar und auf den Punkt
- Kein Marketingsprech, keine Floskeln

Antworte NUR mit validem JSON in diesem Format:
{{
    "title": "Konzept-Titel",
    "sections": [
        {{
            "heading": "Abschnitts-Überschrift",
            "points": ["Erster Punkt als ganzer Satz", "Zweiter Punkt als ganzer Satz"]
        }}
    ]
}}

{ctype['sections_hint']}
Kein Markdown, kein Erklärtext — NUR das JSON."""

    headers = {
        "Authorization": f"Bearer {LANGDOCK_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "agentId": LANGDOCK_AGENT_ID,
        "messages": [{"id": "msg-1", "role": "user", "parts": [{"type": "text", "text": prompt}]}],
        "stream": False,
    }

    response = requests.post(LANGDOCK_URL, headers=headers, json=payload, timeout=120)
    response.raise_for_status()
    data = response.json()

    # Extract text from Langdock response
    raw_text = ""
    for msg in data.get("result", []):
        if msg.get("role") == "assistant":
            for part in msg.get("parts", []):
                if isinstance(part, dict) and part.get("type") == "text":
                    raw_text = part.get("text", "")
            if not raw_text:
                for block in msg.get("content", []):
                    if isinstance(block, dict) and block.get("type") == "text":
                        raw_text = block.get("text", "")
                    elif isinstance(block, str):
                        raw_text = block

    if not raw_text:
        raise RuntimeError("Merlin hat keine Antwort geliefert")

    # Parse JSON from response (handle markdown code blocks)
    if "```" in raw_text:
        match = re.search(r"```(?:json)?\s*(.*?)```", raw_text, re.DOTALL)
        if match:
            raw_text = match.group(1)

    # Clean up common JSON issues from LLM output
    raw_text = raw_text.strip()

    # Try parsing as-is first
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        pass

    # Fix: remove trailing commas before ] or }
    cleaned = re.sub(r',\s*([}\]])', r'\1', raw_text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Fix: escape unescaped quotes inside strings
    # Try to find JSON object in the text
    match = re.search(r'\{.*\}', cleaned, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    # Last resort: let Claude fix the JSON
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=_secret("ANTHROPIC_API_KEY"))
        fix_resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=4096,
            messages=[{"role": "user", "content": f"Fix this broken JSON and return ONLY valid JSON, nothing else:\n\n{raw_text[:4000]}"}],
        )
        fixed = fix_resp.content[0].text.strip()
        if "```" in fixed:
            m = re.search(r"```(?:json)?\s*(.*?)```", fixed, re.DOTALL)
            if m:
                fixed = m.group(1)
        return json.loads(fixed.strip())
    except Exception:
        pass

    raise RuntimeError(f"Merlins Antwort ist kein valides JSON. Bitte nochmal versuchen.")


# Color palette for sections
SECTION_COLORS = [
    {"sticky": "light_blue", "shape": "#0ca789", "label": "Teal"},
    {"sticky": "light_green", "shape": "#8fd14f", "label": "Green"},
    {"sticky": "light_yellow", "shape": "#fac710", "label": "Yellow"},
    {"sticky": "light_pink", "shape": "#f24726", "label": "Red"},
    {"sticky": "violet", "shape": "#9510ac", "label": "Purple"},
    {"sticky": "dark_blue", "shape": "#2d9bf0", "label": "Blue"},
]


def place_concept_on_board(board_id: str, concept: dict, progress_callback=None) -> dict:
    """Place a structured concept on a Miro board.

    All positions use Miro's center-origin coordinate system.
    Layout: Title bar on top, then section columns below it.
    Each column has a colored header shape + sticky notes stacked vertically.
    """
    from miro_bot.miro_api import (
        get_board_items, find_free_area, create_frame,
        create_shape, create_sticky_note, create_connector,
    )

    def update(pct, text):
        if progress_callback:
            progress_callback(pct, text)

    update(0.1, "Board-Elemente laden...")

    existing_items = get_board_items(board_id)
    origin_x, origin_y = find_free_area(existing_items)

    sections = concept.get("sections", [])
    title = concept.get("title", "Konzept")

    # ── Layout config ──
    # NOTE: Miro auto-sizes sticky notes to ~370px tall for short text
    col_width = 380          # width of each section column
    col_gap = 60             # horizontal gap between columns
    header_h = 80            # section header height
    sticky_w = 340           # sticky note width
    sticky_h = 400           # sticky note actual height (Miro auto-sizes to ~370)
    sticky_gap = 50          # vertical gap between stickies
    title_h = 90             # title bar height
    title_margin = 60        # gap between title and sections
    padding = 100            # frame padding around content

    cols = min(len(sections), 3)
    rows = (len(sections) + cols - 1) // cols if cols else 1
    max_points = max((len(s.get("points", [])) for s in sections), default=3)

    # Calculate frame dimensions
    content_w = cols * col_width + (cols - 1) * col_gap
    col_content_h = header_h + sticky_gap + max_points * (sticky_h + sticky_gap)
    content_h = title_h + title_margin + rows * (col_content_h + col_gap)
    frame_w = content_w + padding * 2
    frame_h = content_h + padding * 2

    # Content top-left corner (for placing items inside)
    content_left = origin_x + padding
    content_top = origin_y + padding

    update(0.2, "Frame erstellen...")

    frame = create_frame(board_id, origin_x, origin_y, frame_w, frame_h, title)
    frame_id = frame.get("id", "")

    # ── Title bar (centered horizontally, at top of content) ──
    title_cx = content_left + content_w // 2
    title_cy = content_top + title_h // 2

    create_shape(
        board_id,
        x=title_cx, y=title_cy,
        width=content_w, height=title_h,
        content=f"<strong>{title}</strong>",
        fill_color="#1a1a2e",
        text_color="#ffffff",
        font_size="24",
    )

    items_created = 2
    total_steps = 2 + len(sections) + sum(len(s.get("points", [])) for s in sections)

    # ── Y start for section columns (below title) ──
    sections_top = content_top + title_h + title_margin

    for i, section in enumerate(sections):
        col = i % cols
        row = i // cols
        color = SECTION_COLORS[i % len(SECTION_COLORS)]

        # Column center X
        col_cx = content_left + col * (col_width + col_gap) + col_width // 2

        # Row top Y
        row_top = sections_top + row * (col_content_h + col_gap)

        update(items_created / total_steps, f"Abschnitt: {section['heading'][:30]}...")

        # ── Section header ──
        header_cy = row_top + header_h // 2

        sec_shape = create_shape(
            board_id,
            x=col_cx, y=header_cy,
            width=col_width, height=header_h,
            content=f"<strong>{section['heading']}</strong>",
            fill_color=color["shape"],
            text_color="#ffffff",
            font_size="14",
        )
        sec_shape_id = sec_shape.get("id", "")
        items_created += 1

        # ── Sticky notes below header ──
        prev_id = sec_shape_id
        first_sticky_top = row_top + header_h + sticky_gap

        for j, point in enumerate(section.get("points", [])):
            sticky_cy = first_sticky_top + j * (sticky_h + sticky_gap) + sticky_h // 2

            update(items_created / total_steps, f"  → {point[:40]}...")

            sticky = create_sticky_note(
                board_id,
                x=col_cx, y=sticky_cy,
                content=f"<p>{point}</p>",
                color=color["sticky"],
                width=sticky_w,
            )
            sticky_id = sticky.get("id", "")
            items_created += 1

            # Arrow from header → first sticky, then sticky → sticky
            if prev_id and sticky_id:
                try:
                    create_connector(board_id, prev_id, sticky_id, color=color["shape"])
                    items_created += 1
                except Exception:
                    pass
            prev_id = sticky_id

    update(1.0, "Fertig!")

    return {
        "items_created": items_created,
        "frame_id": frame_id,
        "board_url": f"https://miro.com/app/board/{board_id}/",
        "sections": len(sections),
        "title": title,
    }
