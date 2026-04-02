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


def generate_concept(thema: str, kontext: str = "") -> dict:
    """Ask Merlin (Langdock) to generate a structured concept.

    Returns dict with: title, sections (list of {heading, points, color}).
    """
    if not LANGDOCK_API_KEY or not LANGDOCK_AGENT_ID:
        raise RuntimeError("LANGDOCK_API_KEY oder LANGDOCK_AGENT_ID nicht konfiguriert")

    prompt = f"""Erstelle ein strukturiertes Konzept zum Thema: "{thema}"

{f"Zusätzlicher Kontext: {kontext}" if kontext else ""}

Antworte NUR mit validem JSON in diesem Format:
{{
    "title": "Konzept-Titel",
    "sections": [
        {{
            "heading": "Abschnitts-Überschrift",
            "points": ["Punkt 1", "Punkt 2", "Punkt 3"]
        }},
        {{
            "heading": "Nächster Abschnitt",
            "points": ["Punkt 1", "Punkt 2"]
        }}
    ]
}}

Erstelle 4-6 Abschnitte mit jeweils 2-5 konkreten, actionable Punkten.
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

    return json.loads(raw_text.strip())


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
