import os
import json
import time
import requests
import httpx
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
APIFY_API_TOKEN = _secret("APIFY_API_TOKEN")
APIFY_TIKTOK_ACTOR = "clockworks~tiktok-scraper"
APIFY_GOOGLE_ACTOR = "apify~google-search-scraper"

# Higgsfield (Nano Banana)
HF_API_KEY = _secret("HF_API_KEY")
HF_API_SECRET = _secret("HF_API_SECRET")
HIGGSFIELD_BASE_URL = "https://platform.higgsfield.ai"


# ─── LANGDOCK HELPERS ───────────────────────────────────────────────────────

def _send_to_langdock(prompt: str) -> str:
    """Sends a prompt to Langdock agent and returns the raw text response.
    Handles rate limit retries with 15s increments."""

    headers = {
        "Authorization": f"Bearer {LANGDOCK_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "agentId": LANGDOCK_AGENT_ID,
        "messages": [{"id": "msg-1", "role": "user", "parts": [{"type": "text", "text": prompt}]}],
        "stream": False
    }

    for attempt in range(5):
        response = requests.post(LANGDOCK_URL, headers=headers, json=payload)
        if response.status_code == 429:
            wait = 15 * (attempt + 1)
            print(f"  Rate Limit – warte {wait}s...")
            time.sleep(wait)
            continue
        response.raise_for_status()
        break

    data = response.json()

    raw_text = ""
    for msg in data.get("result", []):
        if msg.get("role") == "assistant":
            for part in msg.get("parts", []):
                if isinstance(part, dict) and part.get("type") == "text":
                    raw_text = part.get("text", "")
                elif isinstance(part, str):
                    raw_text = part
            # Fallback: altes Format mit content
            if not raw_text:
                content = msg.get("content", [])
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        raw_text = block.get("text", "")
                    elif isinstance(block, str):
                        raw_text = block

    return raw_text


def _parse_json_from_langdock(raw_text: str):
    """Extracts JSON from Langdock response, handling markdown code blocks."""
    try:
        if "```" in raw_text:
            raw_text = raw_text.split("```")[1]
            if raw_text.startswith("json"):
                raw_text = raw_text[4:]
        return json.loads(raw_text.strip())
    except json.JSONDecodeError:
        return None


def _build_ci_context(profile: dict) -> str:
    """Builds the CI context string from a profile."""
    colors_str = ", ".join([f"{c['name']}: {c['hex']}" for c in profile.get("colors", [])])
    return f"""
Corporate Identity des Kunden:
- Firma: {profile.get('name', '')}
- Branche: {profile.get('industry', '')}
- Slogan: {profile.get('slogan', '')}
- Zielgruppe: {profile.get('target_audience', '')}
- Tonalitaet: {profile.get('tone', '')}
- Markenwerte: {profile.get('values', '')}
- Markenfarben: {colors_str}
- Schrift: {profile.get('font', '')}
- Sprache: {profile.get('language', 'Deutsch')}
- Hinweise: {profile.get('notes', '')}
"""


# ─── PROFILE LOADING ────────────────────────────────────────────────────────

def load_profile(profile_slug: str) -> dict:
    """Laedt ein Kundenprofil aus data/profiles/."""
    path = f"data/profiles/{profile_slug}.json"
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


# ─── STEP 1: FIND COMPETITORS ───────────────────────────────────────────────

def find_competitors(profile: dict) -> list:
    """Sends profile info to Langdock agent to identify 3-5 key competitors."""

    ci_context = _build_ci_context(profile)

    prompt = f"""Analysiere das folgende Unternehmensprofil und identifiziere 3-5 der wichtigsten Wettbewerber in derselben Branche.

{ci_context}

Gib das Ergebnis als valides JSON-Array zurueck – kein Text davor oder danach, nur JSON.

Das JSON muss exakt diese Struktur haben:
[
  {{"name": "Firmenname", "instagram": "@handle", "tiktok": "@handle"}},
  {{"name": "Firmenname", "instagram": "@handle", "tiktok": "@handle"}}
]

Falls du einen Social-Handle nicht kennst, setze einen leeren String "".
Fokussiere dich auf Wettbewerber, die aktiv auf Social Media (Instagram, TikTok) sind."""

    raw_text = _send_to_langdock(prompt)
    result = _parse_json_from_langdock(raw_text)

    if isinstance(result, list):
        return result

    # Fallback: return empty list
    print(f"  Warnung: Competitors konnten nicht geparst werden.")
    return []


# ─── STEP 2: SCRAPE TRENDS ──────────────────────────────────────────────────

def _run_tiktok_scraper(search_queries: list, max_results: int = 5) -> list:
    """Runs the Apify TikTok scraper with given search queries."""
    if not APIFY_API_TOKEN:
        print("  Warnung: APIFY_API_TOKEN nicht gesetzt, ueberspringe TikTok-Scraping.")
        return []

    run_url = f"https://api.apify.com/v2/acts/{APIFY_TIKTOK_ACTOR}/runs?token={APIFY_API_TOKEN}&waitForFinish=120"
    payload = {
        "searchQueries": search_queries,
        "resultsPerPage": max_results,
        "searchSection": "/video"
    }

    try:
        run_resp = requests.post(run_url, json=payload)
        run_resp.raise_for_status()
        run_data = run_resp.json()
        dataset_id = run_data["data"]["defaultDatasetId"]

        items_url = f"https://api.apify.com/v2/datasets/{dataset_id}/items?token={APIFY_API_TOKEN}&limit={max_results * len(search_queries)}"
        items_resp = requests.get(items_url)
        items_resp.raise_for_status()
        items = items_resp.json()

        results = []
        for item in items:
            url = item.get("webVideoUrl", "")
            if not url:
                continue
            results.append({
                "url": url,
                "description": (item.get("text", "") or "")[:200],
                "author": item.get("authorMeta", {}).get("name", item.get("author", "?")),
                "views": item.get("playCount", 0),
                "likes": item.get("diggCount", 0),
                "platform": "TikTok"
            })
        return results
    except Exception as e:
        print(f"  Warnung: TikTok-Scraping fehlgeschlagen: {e}")
        return []


def scrape_trends(industry: str, competitors: list) -> dict:
    """Uses Apify TikTok scraper to find industry trends, viral formats, and competitor content."""

    print("  Suche Branchen-Trends auf TikTok...")
    industry_trends = _run_tiktok_scraper(
        [f"{industry} trends 2026", f"{industry} marketing"],
        max_results=5
    )

    print("  Suche virale Creative-Formate...")
    viral_formats = _run_tiktok_scraper(
        [f"{industry} creative ads", f"trending {industry} content"],
        max_results=5
    )

    print("  Suche Wettbewerber-Content...")
    competitor_queries = [c.get("name", "") for c in competitors if c.get("name")][:3]
    competitor_content = []
    if competitor_queries:
        competitor_content = _run_tiktok_scraper(competitor_queries, max_results=3)

    return {
        "industry_trends": industry_trends,
        "viral_formats": viral_formats,
        "competitor_content": competitor_content
    }


# ─── STEP 3: SCRAPE NEWS ────────────────────────────────────────────────────

def scrape_news(industry: str, client_name: str) -> list:
    """Uses Apify Google Search scraper to find recent industry news."""
    if not APIFY_API_TOKEN:
        print("  Warnung: APIFY_API_TOKEN nicht gesetzt, ueberspringe News-Scraping.")
        return []

    run_url = f"https://api.apify.com/v2/acts/{APIFY_GOOGLE_ACTOR}/runs?token={APIFY_API_TOKEN}&waitForFinish=120"
    payload = {
        "queries": f"{industry} News 2026\n{client_name} Branche aktuell",
        "maxPagesPerQuery": 1,
        "resultsPerPage": 5
    }

    try:
        run_resp = requests.post(run_url, json=payload)
        run_resp.raise_for_status()
        run_data = run_resp.json()
        dataset_id = run_data["data"]["defaultDatasetId"]

        items_url = f"https://api.apify.com/v2/datasets/{dataset_id}/items?token={APIFY_API_TOKEN}&limit=10"
        items_resp = requests.get(items_url)
        items_resp.raise_for_status()
        items = items_resp.json()

        results = []
        for item in items:
            organic = item.get("organicResults", [])
            for result in organic:
                if len(results) >= 5:
                    break
                results.append({
                    "title": result.get("title", ""),
                    "url": result.get("url", ""),
                    "snippet": result.get("description", "")
                })
            if len(results) >= 5:
                break

        return results[:5]
    except Exception as e:
        print(f"  Warnung: News-Scraping fehlgeschlagen: {e}")
        return []


# ─── STEP 4: PLAN CREATIVES ─────────────────────────────────────────────────

def plan_creatives(profile: dict, trends: dict, news: list, competitors: list, num_creatives: int, notes: str) -> list:
    """Sends all gathered data to Langdock agent to create creative concepts."""

    ci_context = _build_ci_context(profile)

    trends_json = json.dumps(trends, ensure_ascii=False, indent=2)
    news_json = json.dumps(news, ensure_ascii=False, indent=2)
    competitors_json = json.dumps(competitors, ensure_ascii=False, indent=2)

    notes_section = ""
    if notes:
        notes_section = f"\nZusaetzliche Hinweise vom Nutzer:\n{notes}\n"

    prompt = f"""Du bist ein Creative Director fuer Social Media.
Erstelle {num_creatives} Creative-Konzepte basierend auf den folgenden Daten.

{ci_context}

--- WETTBEWERBER ---
{competitors_json}

--- AKTUELLE TRENDS (TikTok) ---
{trends_json}

--- AKTUELLE NEWS ---
{news_json}
{notes_section}

WICHTIG:
- Nutze die Markenfarben des Kunden fuer die Creatives
- Jedes Creative soll sich auf einen konkreten Trend oder eine News beziehen
- Entscheide pro Creative ob ein Text-Overlay sinnvoll ist (basierend auf Trend-Analyse)
- Captions muessen ready-to-post sein, mit passenden Hashtags
- Beruecksichtige die Tonalitaet und Sprache des Kunden

Gib das Ergebnis als valides JSON-Array zurueck – kein Text davor oder danach, nur JSON.

Jedes Creative muss exakt diese Struktur haben:
[
  {{
    "title": "Kurzer Titel des Creatives",
    "type": "feed_post | story | karussell",
    "caption": "Fertige Caption mit Hashtags",
    "text_overlay": {{
      "enabled": true,
      "text": "Text auf dem Bild",
      "position": "top | center | bottom",
      "style": "bold | clean | handwritten"
    }},
    "image_description": "Detaillierte Beschreibung was das Bild zeigen soll",
    "mood": "Visuelle Stimmungsbeschreibung",
    "colors": [
      {{"name": "Primaer", "hex": "#XXXXXX"}},
      {{"name": "Sekundaer", "hex": "#XXXXXX"}},
      {{"name": "Akzent", "hex": "#XXXXXX"}}
    ],
    "reasoning": "Warum dieses Creative gewaehlt wurde (basierend auf welchem Trend/News)",
    "source_references": ["URL1", "URL2"]
  }}
]

Erstelle genau {num_creatives} Creatives."""

    raw_text = _send_to_langdock(prompt)
    result = _parse_json_from_langdock(raw_text)

    if isinstance(result, list):
        return result

    # Fallback
    print(f"  Warnung: Creatives konnten nicht geparst werden.")
    return [{
        "title": "Parse-Fehler",
        "type": "feed_post",
        "caption": "",
        "text_overlay": {"enabled": False, "text": "", "position": "center", "style": "clean"},
        "image_description": raw_text[:500] if raw_text else "Keine Antwort erhalten",
        "mood": "",
        "colors": profile.get("colors", []),
        "reasoning": "Automatischer Fallback wegen Parse-Fehler",
        "source_references": []
    }]


# ─── STEP 5: GENERATE CREATIVE IMAGE ────────────────────────────────────────

def _build_image_prompt(concept: dict, profile: dict) -> str:
    """Builds a detailed image generation prompt from the concept and profile CI.
    Text overlays are NOT included — those go in the separate SVG overlay."""
    colors = concept.get("colors", profile.get("colors", []))
    color_names = []
    for c in colors:
        if isinstance(c, dict):
            color_names.append(f"{c.get('name', '')}: {c.get('hex', '')}")
        elif isinstance(c, str):
            color_names.append(c)
    colors_str = ", ".join(color_names) if color_names else ""

    image_desc = concept.get("image_description", "")
    mood = concept.get("mood", "")
    industry = profile.get("industry", "")

    prompt_parts = []
    prompt_parts.append(f"Professional social media creative for {industry}.")
    if image_desc:
        prompt_parts.append(image_desc)
    if mood:
        prompt_parts.append(f"Mood: {mood}.")
    if colors_str:
        prompt_parts.append(f"Use these brand colors: {colors_str}.")
    prompt_parts.append("High quality, modern design, visually striking, clean background suitable for text overlay. No text on image.")

    return " ".join(prompt_parts)


def _generate_with_higgsfield(prompt: str, aspect_ratio: str = "1:1") -> str:
    """Calls Higgsfield Nano Banana API. Returns the image URL or empty string on failure."""
    if not HF_API_KEY or not HF_API_SECRET:
        print("  Warnung: HF_API_KEY/HF_API_SECRET nicht gesetzt.")
        return ""

    credential_key = f"{HF_API_KEY}:{HF_API_SECRET}"

    client = httpx.Client(
        headers={
            "Authorization": f"Key {credential_key}",
            "Content-Type": "application/json",
        },
        base_url=HIGGSFIELD_BASE_URL,
        timeout=120.0,
    )

    payload = {
        "params": {
            "prompt": prompt,
            "resolution": "2K",
            "aspect_ratio": aspect_ratio,
            "input_images": [],
        }
    }

    try:
        # Submit the generation request
        response = client.post("/v1/text2image/nano-banana", json=payload)
        response.raise_for_status()
        data = response.json()

        job_set_id = data.get("id", data.get("job_set_id", ""))
        if not job_set_id:
            print(f"  Warnung: Keine job_set_id in Higgsfield-Antwort: {data}")
            return ""
        print(f"    Higgsfield Job gestartet: {job_set_id}")

        # Poll for completion
        status_url = f"/v1/job-sets/{job_set_id}"
        for attempt in range(60):  # max 2 Minuten
            time.sleep(2)
            status_resp = client.get(status_url)
            status_resp.raise_for_status()
            status_data = status_resp.json()

            jobs = status_data.get("jobs", [])
            job_status = jobs[0].get("status", "") if jobs else ""
            if job_status == "completed":
                # Extract image URL — structure: jobs[0].results.raw.url
                results = jobs[0].get("results", {})
                raw_url = results.get("raw", {}).get("url", "")
                if raw_url:
                    return raw_url
                # Fallback: try min version
                min_url = results.get("min", {}).get("url", "")
                if min_url:
                    return min_url
                print(f"  Warnung: Keine Bilder in Ergebnis: {status_data}")
                return ""
            elif job_status in ("failed", "canceled"):
                print(f"  Fehler: Higgsfield Job {job_status}: {status_data}")
                return ""
            # else: still in progress

        print("  Warnung: Higgsfield Timeout nach 2 Minuten.")
        return ""

    except httpx.HTTPStatusError as e:
        print(f"  Fehler: Higgsfield API {e.response.status_code}: {e.response.text}")
        return ""
    except Exception as e:
        print(f"  Fehler: Higgsfield Anfrage fehlgeschlagen: {e}")
        return ""
    finally:
        client.close()


def _download_image(url: str, save_path: str) -> bool:
    """Downloads an image from a URL and saves it locally."""
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        with open(save_path, "wb") as f:
            f.write(response.content)
        return True
    except Exception as e:
        print(f"  Warnung: Bild-Download fehlgeschlagen: {e}")
        return False


def _generate_text_overlay_svg(concept: dict, profile: dict, width: int, height: int) -> str:
    """Generates an SVG with editable text elements (overlay, brand name, logo placeholder).
    Transparent background — meant to be layered on top of the AI image in Canva."""

    font = profile.get("font", "Inter, Helvetica, Arial, sans-serif").split(",")[0].strip()
    client_name = _svg_escape(profile.get("name", "Brand"))

    colors = concept.get("colors", profile.get("colors", []))
    if isinstance(colors, list) and len(colors) > 1:
        accent = colors[1]["hex"] if isinstance(colors[1], dict) else colors[1]
    else:
        accent = "#ffffff"

    overlay = concept.get("text_overlay", {})
    overlay_enabled = overlay.get("enabled", False)
    overlay_text = _svg_escape(overlay.get("text", ""))
    overlay_position = overlay.get("position", "center")
    overlay_style = overlay.get("style", "clean")

    # Overlay Y position
    pos_y = {"top": int(height * 0.18), "center": int(height * 0.48), "bottom": int(height * 0.78)}
    oy = pos_y.get(overlay_position, pos_y["center"])

    # Overlay font style
    style_map = {
        "bold": f'font-weight="900" font-size="64" letter-spacing="2" font-family="{font}"',
        "clean": f'font-weight="600" font-size="52" font-family="{font}"',
        "handwritten": 'font-weight="400" font-size="56" font-style="italic" font-family="Georgia, serif"',
    }
    overlay_attrs = style_map.get(overlay_style, style_map["clean"])

    # Build text overlay
    overlay_svg = ""
    if overlay_enabled and overlay_text:
        words = overlay_text.split()
        lines, current = [], ""
        for w in words:
            if len(current) + len(w) + 1 > 28:
                lines.append(current.strip())
                current = w
            else:
                current += " " + w
        if current.strip():
            lines.append(current.strip())

        tspans = ""
        for i, line in enumerate(lines):
            dy = "0" if i == 0 else "1.2em"
            tspans += f'<tspan x="{width // 2}" dy="{dy}">{line}</tspan>'

        # Text with shadow for readability
        overlay_svg = f"""
  <text x="{width // 2}" y="{oy + 2}" text-anchor="middle" fill="rgba(0,0,0,0.4)"
        {overlay_attrs}>
      {tspans}
  </text>
  <text x="{width // 2}" y="{oy}" text-anchor="middle" fill="#ffffff"
        {overlay_attrs}>
      {tspans}
  </text>"""

    # Brand name top-left
    brand_svg = f"""
  <text x="32" y="46" font-family="{font}" font-size="24" font-weight="800"
        fill="#ffffff" letter-spacing="1">{client_name}</text>"""

    # Logo placeholder circle top-right
    logo_svg = f"""
  <circle cx="{width - 52}" cy="38" r="24" fill="{accent}" opacity="0.9"/>
  <text x="{width - 52}" y="44" text-anchor="middle" font-family="{font}"
        font-size="14" font-weight="700" fill="#ffffff">LOGO</text>"""

    svg = f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}">
  <!-- Transparent overlay — import into Canva on top of AI image -->
  {brand_svg}
  {logo_svg}
  {overlay_svg}
</svg>"""

    return svg


def generate_creative_image(concept: dict, profile: dict):
    """Generates an AI image via Higgsfield Nano Banana + a separate editable SVG overlay.
    Returns (png_path, svg_overlay_path)."""

    os.makedirs("outputs/creatives", exist_ok=True)

    creative_type = concept.get("type", "feed_post")
    aspect_ratio = "9:16" if creative_type == "story" else "1:1"
    width = 1080
    height = 1920 if creative_type == "story" else 1080

    # Build prompt from concept + CI (no text — text goes in SVG overlay)
    prompt = _build_image_prompt(concept, profile)
    print(f"    Prompt: {prompt[:100]}...")

    safe_title = "".join(c if c.isalnum() or c in "_- " else "" for c in concept.get("title", "creative")).strip().replace(" ", "_")[:40]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    png_filename = f"{safe_title}_{timestamp}.png"
    png_path = os.path.join("outputs", "creatives", png_filename)

    # Always generate the SVG text overlay
    overlay_svg = _generate_text_overlay_svg(concept, profile, width, height)
    svg_filename = f"{safe_title}_{timestamp}_overlay.svg"
    svg_path = os.path.join("outputs", "creatives", svg_filename)
    with open(svg_path, "w", encoding="utf-8") as f:
        f.write(overlay_svg)

    # Try Higgsfield Nano Banana for the image
    image_url = _generate_with_higgsfield(prompt, aspect_ratio)

    if image_url:
        if _download_image(image_url, png_path):
            print(f"    KI-Bild: {png_path}")
            print(f"    SVG-Overlay: {svg_path}")
            return png_path, svg_path

    # Fallback: Generate SVG placeholder as PNG substitute
    print("    Higgsfield nicht verfuegbar, verwende SVG-Fallback...")
    fallback_svg_path, _ = _generate_fallback_svg(concept, profile, safe_title, timestamp)
    return fallback_svg_path, svg_path


def _generate_fallback_svg(concept: dict, profile: dict, safe_title: str, timestamp: str):
    """Generates a simple SVG fallback creative. Returns (svg_path, png_path)."""
    creative_type = concept.get("type", "feed_post")
    width = 1080
    height = 1920 if creative_type == "story" else 1080

    colors = concept.get("colors", profile.get("colors", []))
    if isinstance(colors, list) and colors:
        bg_color = (colors[0]["hex"] if isinstance(colors[0], dict) else colors[0]) if len(colors) > 0 else "#1a1a2e"
        secondary = (colors[1]["hex"] if isinstance(colors[1], dict) else colors[1]) if len(colors) > 1 else "#e63946"
        accent = (colors[2]["hex"] if isinstance(colors[2], dict) else colors[2]) if len(colors) > 2 else "#ffffff"
    else:
        bg_color, secondary, accent = "#1a1a2e", "#e63946", "#ffffff"
    bg_dark = _darken_hex(bg_color, 30)

    client_name = _svg_escape(profile.get("name", "Brand"))
    font = profile.get("font", "Inter, Helvetica, Arial, sans-serif").split(",")[0].strip()
    mood = _svg_escape(concept.get("mood", ""))

    overlay = concept.get("text_overlay", {})
    overlay_text = _svg_escape(overlay.get("text", "")) if overlay.get("enabled") else ""

    # Build overlay SVG
    overlay_svg = ""
    if overlay_text:
        oy = int(height * 0.48)
        words = overlay_text.split()
        lines, current = [], ""
        for w in words:
            if len(current) + len(w) + 1 > 28:
                lines.append(current.strip())
                current = w
            else:
                current += " " + w
        if current.strip():
            lines.append(current.strip())
        tspans = ""
        for i, line in enumerate(lines):
            dy = "0" if i == 0 else "1.2em"
            tspans += f'<tspan x="{width // 2}" dy="{dy}">{line}</tspan>'
        overlay_svg = f"""
    <text x="{width // 2}" y="{oy}" text-anchor="middle" fill="#ffffff"
          font-weight="600" font-size="52" font-family="{font}" opacity="0.95">
        {tspans}
    </text>"""

    svg = f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}">
  <defs>
    <linearGradient id="bgGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="{bg_color}"/>
      <stop offset="100%" stop-color="{bg_dark}"/>
    </linearGradient>
  </defs>
  <rect width="{width}" height="{height}" fill="url(#bgGrad)"/>
  <circle cx="{width + 50}" cy="-50" r="350" fill="{secondary}" opacity="0.12"/>
  <circle cx="-80" cy="{height + 30}" r="250" fill="{accent}" opacity="0.10"/>
  <rect x="0" y="0" width="{width}" height="6" fill="{secondary}"/>
  <text x="32" y="46" font-family="{font}" font-size="22" font-weight="800"
        fill="#ffffff" opacity="0.9">{client_name}</text>
  <text x="{width // 2}" y="{height // 2 - 20}" text-anchor="middle"
        font-family="{font}" font-size="16" fill="rgba(255,255,255,0.4)">
    SVG Fallback – KI-Bild nicht verfuegbar
  </text>
  {overlay_svg}
  <text x="{width // 2}" y="{height - 70}" text-anchor="middle"
        font-family="{font}" font-size="14" fill="rgba(255,255,255,0.35)">{mood}</text>
  <rect x="0" y="{height - 6}" width="{width // 3}" height="6" fill="{bg_color}"/>
  <rect x="{width // 3}" y="{height - 6}" width="{width // 3}" height="6" fill="{secondary}"/>
  <rect x="{width * 2 // 3}" y="{height - 6}" width="{width // 3 + 1}" height="6" fill="{accent}"/>
</svg>"""

    svg_filename = f"{safe_title}_{timestamp}.svg"
    svg_path = os.path.join("outputs", "creatives", svg_filename)
    with open(svg_path, "w", encoding="utf-8") as f:
        f.write(svg)

    return svg_path, ""


def _svg_escape(text: str) -> str:
    """Escapes special characters for SVG text elements."""
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;").replace("'", "&#39;")


def _darken_hex(hex_color: str, amount: int = 30) -> str:
    """Darkens a hex color by a given amount."""
    hex_color = hex_color.lstrip("#")
    if len(hex_color) != 6:
        return "#111111"
    try:
        r = max(0, int(hex_color[0:2], 16) - amount)
        g = max(0, int(hex_color[2:4], 16) - amount)
        b = max(0, int(hex_color[4:6], 16) - amount)
        return f"#{r:02x}{g:02x}{b:02x}"
    except ValueError:
        return "#111111"


# ─── STEP 6: MAIN ORCHESTRATOR ──────────────────────────────────────────────

def run_creative_pipeline(profile_slug: str, num_creatives: int = 0, weeks: int = 1, posts_per_week: int = 3, notes: str = "") -> str:
    """Main orchestrator: loads profile, runs all steps, saves results."""

    print(f"\n{'='*60}")
    print(f"  CREATIVE PIPELINE")
    print(f"{'='*60}\n")

    # Load profile
    profile = load_profile(profile_slug)
    if not profile:
        print(f"  Fehler: Profil '{profile_slug}' nicht gefunden.")
        return ""
    print(f"  Profil geladen: {profile.get('name', profile_slug)}")

    # Calculate total creatives
    total = num_creatives if num_creatives > 0 else weeks * posts_per_week
    print(f"  Ziel: {total} Creatives\n")

    # Step 1: Find competitors
    print("[1/5] Wettbewerber identifizieren...")
    competitors = find_competitors(profile)
    print(f"  {len(competitors)} Wettbewerber gefunden:")
    for c in competitors:
        print(f"    - {c.get('name', '?')} (IG: {c.get('instagram', '-')}, TT: {c.get('tiktok', '-')})")

    # Step 2: Scrape trends
    print(f"\n[2/5] Trends scrapen...")
    industry = profile.get("industry", "Social Media Marketing")
    trends = scrape_trends(industry, competitors)
    trend_count = sum(len(v) for v in trends.values())
    print(f"  {trend_count} Trend-Inhalte gefunden")
    for key, items in trends.items():
        print(f"    - {key}: {len(items)} Ergebnisse")

    # Step 3: Scrape news
    print(f"\n[3/5] News scrapen...")
    client_name = profile.get("name", profile_slug)
    news = scrape_news(industry, client_name)
    print(f"  {len(news)} News-Artikel gefunden")
    for n in news:
        print(f"    - {n.get('title', '?')[:60]}")

    # Step 4: Plan creatives
    print(f"\n[4/5] Creative-Konzepte erstellen ({total} Stueck)...")
    creatives = plan_creatives(profile, trends, news, competitors, total, notes)
    print(f"  {len(creatives)} Konzepte erstellt:")
    for i, c in enumerate(creatives):
        print(f"    {i+1}. [{c.get('type', '?')}] {c.get('title', '?')}")

    # Step 5: Generate AI images + SVG overlays
    print(f"\n[5/5] KI-Bilder generieren (Nano Banana) + SVG-Overlays...")
    generated_files = []
    for i, concept in enumerate(creatives):
        print(f"  Creative {i+1}/{len(creatives)}: {concept.get('title', '?')}")
        image_path, svg_overlay_path = generate_creative_image(concept, profile)
        generated_files.append(image_path)
        concept["png_path"] = image_path if image_path.endswith(".png") else ""
        concept["svg_path"] = svg_overlay_path
        # Keep fallback SVG as png_path if no PNG was generated
        if not concept["png_path"] and image_path.endswith(".svg"):
            concept["svg_path"] = image_path
        print(f"    -> {image_path}")

    # Build result
    result = {
        "client": client_name,
        "profile_slug": profile_slug,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "notes": notes,
        "competitors": competitors,
        "trends_summary": {
            "industry_trends": len(trends.get("industry_trends", [])),
            "viral_formats": len(trends.get("viral_formats", [])),
            "competitor_content": len(trends.get("competitor_content", []))
        },
        "trends_raw": trends,
        "news": news,
        "creatives": creatives,
        "generated_files": generated_files
    }

    # Save output
    os.makedirs("outputs/creatives", exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    output_path = f"outputs/creatives/{profile_slug}_{timestamp}.json"

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, ensure_ascii=False, indent=2, fp=f)

    # Also save as latest
    latest_path = f"outputs/creatives/latest_{profile_slug}.json"
    with open(latest_path, "w", encoding="utf-8") as f:
        json.dump(result, ensure_ascii=False, indent=2, fp=f)

    print(f"\n{'='*60}")
    print(f"  Pipeline fertig!")
    print(f"  Output: {output_path}")
    print(f"  Latest: {latest_path}")
    print(f"  {len(generated_files)} Creatives generiert")
    print(f"{'='*60}\n")

    return output_path


# ─── CLI ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    profile_slug = sys.argv[1] if len(sys.argv) > 1 else "niro_media"
    num_creatives = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    weeks = int(sys.argv[3]) if len(sys.argv) > 3 else 1
    posts_per_week = int(sys.argv[4]) if len(sys.argv) > 4 else 3
    notes = sys.argv[5] if len(sys.argv) > 5 else ""

    run_creative_pipeline(profile_slug, num_creatives, weeks, posts_per_week, notes)
