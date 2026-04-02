"""
Template Bot — copies Miro templates and fills empty shapes with Merlin's content.
Reads templates from a template board, identifies empty shapes, generates content via Merlin,
then recreates everything on the target board.
"""
import json
import re
import requests
import os
from html import unescape
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

TEMPLATE_BOARD_ID = "uXjVJWxGfj4="


def _clean_html(html: str) -> str:
    """Strip HTML tags and decode entities."""
    text = unescape(html or "")
    return re.sub(r'<[^>]+>', '', text).strip()


def read_templates(board_id: str = TEMPLATE_BOARD_ID) -> dict:
    """Read template board and identify templates by their title bars (#ffc6c6).

    Returns dict: { "template_name": { "title_item": ..., "items": [...], "fields": [...] } }
    """
    from miro_bot.miro_api import get_board_items

    all_items = get_board_items(board_id)

    # Find title bars (pink #ffc6c6 shapes) — these define templates
    title_bars = []
    for item in all_items:
        if item.get("type") == "shape":
            fill = item.get("style", {}).get("fillColor", "")
            if fill == "#ffc6c6":
                content = _clean_html(item.get("data", {}).get("content", ""))
                if content:
                    title_bars.append({
                        "name": content.rstrip(":").strip(),
                        "x": item["position"]["x"],
                        "y": item["position"]["y"],
                        "width": item["geometry"]["width"],
                        "item": item,
                    })

    if not title_bars:
        return {}

    # Sort by x position
    title_bars.sort(key=lambda t: t["x"])

    # Assign items to templates based on x-range
    templates = {}
    for i, tb in enumerate(title_bars):
        # Template x-range: from this title bar to the next one (or infinity)
        x_min = tb["x"] - tb["width"] / 2 - 50
        x_max = title_bars[i + 1]["x"] - title_bars[i + 1]["width"] / 2 - 50 if i + 1 < len(title_bars) else float("inf")

        template_items = []
        fields = []  # empty shapes that need filling

        for item in all_items:
            ix = item.get("position", {}).get("x", 0)
            if x_min <= ix < x_max:
                # Skip legend area (small 40x40 shapes near top)
                geo = item.get("geometry", {})
                if geo.get("width", 0) <= 40 and geo.get("height", 0) <= 40:
                    continue

                template_items.append(item)

                # Identify empty fill shapes (shapes with no text content, not gray helpers)
                if item.get("type") == "shape":
                    content = _clean_html(item.get("data", {}).get("content", ""))
                    fill = item.get("style", {}).get("fillColor", "")
                    w = geo.get("width", 0)
                    h = geo.get("height", 0)

                    if not content and fill != "#e7e7e7" and w > 100 and h > 50:
                        # Find the nearest label above this shape
                        label = _find_label_for_shape(item, all_items, x_min, x_max)
                        fields.append({
                            "item_id": item["id"],
                            "x": item["position"]["x"],
                            "y": item["position"]["y"],
                            "width": w,
                            "height": h,
                            "fill_color": fill,
                            "label": label,
                        })

        templates[tb["name"]] = {
            "title_item": tb["item"],
            "items": template_items,
            "fields": fields,
            "x_min": x_min,
            "x_max": x_max,
        }

    return templates


def _find_label_for_shape(empty_shape: dict, all_items: list,
                          x_min: float, x_max: float) -> str:
    """Find the nearest labeled shape above an empty shape to identify what it is."""
    ex = empty_shape["position"]["x"]
    ey = empty_shape["position"]["y"]

    best_label = ""
    best_dist = float("inf")

    for item in all_items:
        if item["id"] == empty_shape["id"]:
            continue
        if item.get("type") not in ("shape", "text"):
            continue

        ix = item.get("position", {}).get("x", 0)
        iy = item.get("position", {}).get("y", 0)

        if not (x_min <= ix < x_max):
            continue

        content = _clean_html(item.get("data", {}).get("content", ""))
        if not content:
            continue

        # Must be above or at same height, and close horizontally
        if iy < ey and abs(ix - ex) < 300:
            dist = abs(ey - iy) + abs(ix - ex) * 0.5
            if dist < best_dist:
                best_dist = dist
                best_label = content

    return best_label


def generate_content_for_fields(fields: list, thema: str, template_name: str,
                                profile: dict = None, kontext: str = "",
                                file_text: str = "") -> dict:
    """Ask Merlin to generate content for each empty template field.

    Returns dict: { field_label: "generated content" }
    """
    if not LANGDOCK_API_KEY or not LANGDOCK_AGENT_ID:
        raise RuntimeError("LANGDOCK_API_KEY oder LANGDOCK_AGENT_ID nicht konfiguriert")

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

    field_list = "\n".join(f'- "{f["label"]}"' for f in fields if f["label"])

    prompt = f"""Du füllst ein {template_name} aus zum Thema: "{thema}"

{profile_block}

{f"Zusätzlicher Kontext: {kontext}" if kontext else ""}

{("Dokument-Inhalt:" + chr(10) + file_text[:5000]) if file_text else ""}

Folgende Felder müssen ausgefüllt werden:
{field_list}

WICHTIGE REGELN:
- Schreibe natürlich und menschlich, KEINE AI-Sprache
- KEINE Gedankenstriche am Satzanfang
- KEINE Aufzählungszeichen oder Bulletpoints
- Formuliere in kurzen, klaren Sätzen oder Absätzen
- Direkt und auf den Punkt, kein Marketingsprech
- Passe den Inhalt zum jeweiligen Feld an (z.B. bei "Zielgruppe" die Zielgruppe beschreiben)

Antworte NUR mit validem JSON als Object — Keys sind die Feldnamen, Values der Inhalt:
{{
    "Feldname 1": "Inhalt für dieses Feld",
    "Feldname 2": "Inhalt für dieses Feld"
}}

NUR JSON, kein Markdown, kein Erklärtext."""

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

    # Parse JSON
    if "```" in raw_text:
        match = re.search(r"```(?:json)?\s*(.*?)```", raw_text, re.DOTALL)
        if match:
            raw_text = match.group(1)

    raw_text = raw_text.strip()

    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        cleaned = re.sub(r',\s*([}\]])', r'\1', raw_text)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        # Claude fallback
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=_secret("ANTHROPIC_API_KEY"))
            fix_resp = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=4096,
                messages=[{"role": "user", "content": f"Fix this broken JSON and return ONLY valid JSON:\n\n{raw_text[:4000]}"}],
            )
            fixed = fix_resp.content[0].text.strip()
            if "```" in fixed:
                m = re.search(r"```(?:json)?\s*(.*?)```", fixed, re.DOTALL)
                if m:
                    fixed = m.group(1)
            return json.loads(fixed.strip())
        except Exception:
            pass

    raise RuntimeError("Merlins Antwort ist kein valides JSON. Bitte nochmal versuchen.")


def place_template_on_board(target_board_id: str, template_name: str,
                            generated_content: dict, templates: dict = None,
                            progress_callback=None) -> dict:
    """Copy a template to the target board and fill empty shapes with generated content.

    Args:
        target_board_id: Miro board to place the filled template on
        template_name: Name of the template to use
        generated_content: dict of { field_label: "content" } from generate_content_for_fields
        templates: Pre-loaded templates dict (optional, will read if not provided)
        progress_callback: optional fn(progress_float, status_text)
    """
    from miro_bot.miro_api import (
        get_board_items, find_free_area,
        create_shape, create_text, create_frame,
    )

    def update(pct, text):
        if progress_callback:
            progress_callback(min(pct, 1.0), text)

    if templates is None:
        update(0.05, "Templates laden...")
        templates = read_templates()

    if template_name not in templates:
        raise RuntimeError(f"Template '{template_name}' nicht gefunden. Verfügbar: {list(templates.keys())}")

    template = templates[template_name]
    items = template["items"]
    fields = template["fields"]

    update(0.1, "Ziel-Board analysieren...")
    existing = get_board_items(target_board_id)
    offset_x, offset_y = find_free_area(existing)

    # Calculate template origin (top-left of template items)
    all_x = [i["position"]["x"] - i["geometry"].get("width", 0) / 2 for i in items]
    all_y = [i["position"]["y"] - i["geometry"].get("height", 0) / 2 for i in items]
    tpl_origin_x = min(all_x) if all_x else 0
    tpl_origin_y = min(all_y) if all_y else 0

    # Build field lookup by item_id
    field_by_id = {f["item_id"]: f for f in fields}

    # Match generated content to fields (fuzzy match on label)
    content_by_id = {}
    for field in fields:
        label = field["label"]
        # Try exact match first, then partial
        matched = generated_content.get(label, "")
        if not matched:
            for key, val in generated_content.items():
                if key.lower() in label.lower() or label.lower() in key.lower():
                    matched = val
                    break
        content_by_id[field["item_id"]] = matched

    update(0.2, "Template kopieren...")

    items_created = 0
    total = len(items)

    for i, item in enumerate(sorted(items, key=lambda x: (x["position"]["y"], x["position"]["x"]))):
        typ = item.get("type")
        pos = item.get("position", {})
        geo = item.get("geometry", {})
        style = item.get("style", {})
        data = item.get("data", {})

        # Calculate new position
        new_x = int(pos.get("x", 0) - tpl_origin_x + offset_x)
        new_y = int(pos.get("y", 0) - tpl_origin_y + offset_y)
        w = int(geo.get("width", 200))
        h = int(geo.get("height", 50))

        progress = 0.2 + 0.8 * (i / total)
        update(progress, f"Element {i + 1}/{total}...")

        try:
            if typ == "shape":
                content = data.get("content", "")
                fill = style.get("fillColor", "#ffffff")

                # Fill empty shapes with generated content
                if item["id"] in content_by_id and content_by_id[item["id"]]:
                    content = f"<p>{content_by_id[item['id']]}</p>"

                # Determine text color based on fill
                text_color = style.get("color", "#1a1a2e")
                font_size = style.get("fontSize", "14")

                create_shape(
                    target_board_id,
                    x=new_x, y=new_y,
                    width=w, height=max(h, 20),
                    content=content,
                    fill_color=fill,
                    text_color=text_color,
                    font_size=font_size,
                    shape=data.get("shape", "round_rectangle"),
                )
                items_created += 1

            elif typ == "text":
                content = data.get("content", "")
                color = style.get("color", "#1a1a2e")
                font_size = style.get("fontSize", "14")

                create_text(
                    target_board_id,
                    x=new_x, y=new_y,
                    content=content,
                    font_size=font_size,
                    color=color,
                    width=w if w > 0 else 200,
                )
                items_created += 1

        except Exception as e:
            # Skip items that fail (e.g. unsupported types)
            continue

    update(1.0, "Fertig!")

    return {
        "items_created": items_created,
        "template_name": template_name,
        "fields_filled": sum(1 for v in content_by_id.values() if v),
        "board_url": f"https://miro.com/app/board/{target_board_id}/",
    }
