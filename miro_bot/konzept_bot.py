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

    Args:
        board_id: Miro board ID
        concept: dict with title and sections from generate_concept()
        progress_callback: optional fn(progress_float, status_text)

    Returns: dict with stats (items_created, frame_id, board_url)
    """
    from miro_bot.miro_api import (
        get_board_items, find_free_area, create_frame,
        create_shape, create_sticky_note, create_connector,
    )

    def update(pct, text):
        if progress_callback:
            progress_callback(pct, text)

    update(0.1, "Board-Elemente laden...")

    # Find free space
    existing_items = get_board_items(board_id)
    start_x, start_y = find_free_area(existing_items)

    sections = concept.get("sections", [])
    title = concept.get("title", "Konzept")

    # Layout constants
    cols = min(len(sections), 3)
    col_width = 380
    col_gap = 40
    header_height = 80
    sticky_height = 150
    sticky_gap = 20
    frame_padding = 60

    # Calculate max stickies in any column to size the frame
    max_points = max(len(s.get("points", [])) for s in sections) if sections else 3
    rows = (len(sections) + cols - 1) // cols

    total_width = cols * col_width + (cols - 1) * col_gap + frame_padding * 2
    row_height = header_height + max_points * (sticky_height + sticky_gap) + 60
    total_height = 120 + rows * row_height + frame_padding

    update(0.2, "Frame erstellen...")

    # Create main frame
    frame = create_frame(board_id, start_x, start_y, total_width, total_height, title)
    frame_id = frame.get("id", "")

    # Title shape
    title_shape = create_shape(
        board_id,
        x=start_x + total_width // 2,
        y=start_y + 50,
        width=total_width - frame_padding * 2,
        height=70,
        content=f"<strong>{title}</strong>",
        fill_color="#1a1a2e",
        text_color="#ffffff",
        font_size="28",
    )

    items_created = 2  # frame + title
    total_steps = 2 + len(sections) + sum(len(s.get("points", [])) for s in sections)

    # Place sections
    all_section_shape_ids = []

    for i, section in enumerate(sections):
        col = i % cols
        row = i // cols
        color = SECTION_COLORS[i % len(SECTION_COLORS)]

        # Section position
        sec_x = start_x + frame_padding + col * (col_width + col_gap) + col_width // 2
        sec_y = start_y + 120 + row * row_height + header_height // 2

        update(items_created / total_steps, f"Abschnitt: {section['heading'][:30]}...")

        # Section header shape
        sec_shape = create_shape(
            board_id,
            x=sec_x, y=sec_y,
            width=col_width, height=header_height,
            content=f"<strong>{section['heading']}</strong>",
            fill_color=color["shape"],
            text_color="#ffffff",
            font_size="16",
        )
        sec_shape_id = sec_shape.get("id", "")
        all_section_shape_ids.append(sec_shape_id)
        items_created += 1

        # Sticky notes for each point
        prev_id = sec_shape_id
        for j, point in enumerate(section.get("points", [])):
            sticky_y = sec_y + header_height // 2 + 30 + j * (sticky_height + sticky_gap) + sticky_height // 2

            update(items_created / total_steps, f"  → {point[:40]}...")

            sticky = create_sticky_note(
                board_id,
                x=sec_x, y=sticky_y,
                content=point,
                color=color["sticky"],
                width=col_width - 20,
            )
            sticky_id = sticky.get("id", "")
            items_created += 1

            # Connect to header or previous sticky
            if prev_id:
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
