import streamlit as st
import json
import os
import glob
import requests
import pdfplumber
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()


def get_secret(key: str, default: str = "") -> str:
    """Get secret from st.secrets (Cloud) or os.environ (.env local)."""
    try:
        return st.secrets[key]
    except Exception:
        return os.getenv(key, default)


LANGDOCK_API_KEY = get_secret("LANGDOCK_API_KEY")
LANGDOCK_AGENT_ID = get_secret("LANGDOCK_AGENT_ID")
LANGDOCK_URL = "https://api.langdock.com/agent/v1/chat/completions"
PROFILES_DIR = "data/profiles"

# ─── CUSTOM CSS ──────────────────────────────────────────────────────────────

CUSTOM_CSS = """
<style>
    /* Hintergrund */
    .stApp { background-color: #0f0f0f; color: #ffffff; }

    /* Sidebar */
    [data-testid="stSidebar"] { background-color: #1a1a1a; }

    /* Content Cards */
    .content-card {
        background: #1e1e1e;
        border: 1px solid #2a2a2a;
        border-radius: 16px;
        padding: 24px;
        margin-bottom: 20px;
        transition: all 0.2s ease;
    }
    .content-card:hover { border-color: #e63946; }

    /* Platform Badge */
    .platform-badge {
        display: inline-block;
        background: #e63946;
        color: white;
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 12px;
        font-weight: 700;
        margin-right: 6px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }

    /* Format Badge */
    .format-badge {
        display: inline-block;
        background: #2a2a2a;
        color: #aaa;
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 12px;
        margin-right: 6px;
    }

    /* Hook Box */
    .hook-box {
        background: linear-gradient(135deg, #e63946 0%, #c1121f 100%);
        border-radius: 12px;
        padding: 16px 20px;
        margin: 12px 0;
        font-size: 18px;
        font-weight: 700;
        font-style: italic;
    }

    /* Caption Box */
    .caption-box {
        background: #252525;
        border-left: 3px solid #e63946;
        border-radius: 0 8px 8px 0;
        padding: 14px 18px;
        font-size: 14px;
        line-height: 1.7;
        color: #cccccc;
    }

    /* Color Swatch */
    .color-swatch {
        width: 40px;
        height: 40px;
        border-radius: 8px;
        display: inline-block;
        margin-right: 8px;
        border: 2px solid #333;
    }

    /* Shot Item */
    .shot-item {
        background: #252525;
        border-radius: 8px;
        padding: 10px 14px;
        margin: 6px 0;
        font-size: 13px;
        color: #cccccc;
    }

    /* Effort Badge */
    .effort-low { color: #2ecc71; font-weight: 700; }
    .effort-mid { color: #f39c12; font-weight: 700; }
    .effort-high { color: #e74c3c; font-weight: 700; }

    /* Section Headers */
    .section-label {
        font-size: 11px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 1.5px;
        color: #666;
        margin-bottom: 8px;
    }

    /* Time Badge */
    .time-badge {
        background: #1a2634;
        color: #4fa3e0;
        padding: 4px 10px;
        border-radius: 6px;
        font-size: 13px;
        font-weight: 600;
    }

    /* Week Header */
    .week-header {
        background: linear-gradient(90deg, #e63946 0%, transparent 100%);
        padding: 12px 20px;
        border-radius: 8px;
        font-size: 20px;
        font-weight: 800;
        margin: 30px 0 16px 0;
    }

    /* Stats Bar */
    .stat-chip {
        display: inline-block;
        background: #252525;
        border-radius: 8px;
        padding: 8px 14px;
        margin: 4px;
        font-size: 13px;
        text-align: center;
    }

    /* App Card (Landing Page) */
    .app-card {
        background: #1e1e1e;
        border: 1px solid #2a2a2a;
        border-radius: 16px;
        padding: 32px;
        text-align: center;
        transition: all 0.2s ease;
        height: 100%;
    }
    .app-card:hover { border-color: #e63946; }
    .app-card .icon { font-size: 48px; margin-bottom: 12px; }
    .app-card .title { font-size: 18px; font-weight: 700; margin-bottom: 8px; }
    .app-card .desc { font-size: 13px; color: #888; }

    h1, h2, h3 { color: #ffffff; }

    /* Scrollbar */
    ::-webkit-scrollbar { width: 6px; }
    ::-webkit-scrollbar-track { background: #1a1a1a; }
    ::-webkit-scrollbar-thumb { background: #e63946; border-radius: 3px; }
</style>
"""

def inject_css():
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


# ─── HELPER FUNCTIONS ────────────────────────────────────────────────────────

def load_latest_plan():
    path = "outputs/latest.json"
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None

def load_all_plans():
    plans = []
    if os.path.exists("outputs"):
        for f in os.listdir("outputs"):
            if f.endswith(".json") and f != "latest.json":
                plans.append(f)
    return sorted(plans, reverse=True)


def load_plan_by_filename(filename: str):
    path = os.path.join("outputs", filename)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return {"client": filename.split("_")[0], "generated_at": "", "profile": "", "plan": data}
        return data
    return None


def effort_badge(effort: str) -> str:
    mapping = {
        "niedrig": ("🟢", "effort-low"),
        "low": ("🟢", "effort-low"),
        "mittel": ("🟡", "effort-mid"),
        "medium": ("🟡", "effort-mid"),
        "hoch": ("🔴", "effort-high"),
        "high": ("🔴", "effort-high"),
    }
    key = effort.lower() if effort else ""
    emoji, css = mapping.get(key, ("⚪", ""))
    return f'<span class="{css}">{emoji} {effort}</span>'

def platform_badges(platforms) -> str:
    if isinstance(platforms, str):
        platforms = [platforms]
    return " ".join([f'<span class="platform-badge">{p}</span>' for p in platforms])

def render_color_swatches(colors: list) -> str:
    if not colors:
        return ""
    html = ""
    for c in colors:
        hex_code = c.get("hex", "#333")
        name = c.get("name", "")
        html += f'''
        <div style="display:inline-block; text-align:center; margin-right:16px;">
            <div style="width:44px;height:44px;background:{hex_code};
                        border-radius:10px;border:2px solid #333;margin-bottom:4px;"></div>
            <div style="font-size:11px;color:#888;">{name}</div>
            <div style="font-size:10px;color:#555;">{hex_code}</div>
        </div>'''
    return html

def render_shot_list(shots: list) -> str:
    if not shots:
        return ""
    html = ""
    for shot in shots:
        num = shot.get("number", "?")
        desc = shot.get("description", "")
        html += f'<div class="shot-item">🎬 <b>Shot {num}:</b> {desc}</div>'
    return html


# ─── PROFILE FUNCTIONS ───────────────────────────────────────────────────────

def load_profiles() -> dict:
    profiles = {}
    os.makedirs(PROFILES_DIR, exist_ok=True)
    for fp in glob.glob(os.path.join(PROFILES_DIR, "*.json")):
        with open(fp, "r", encoding="utf-8") as f:
            data = json.load(f)
            profiles[data.get("slug", os.path.basename(fp).replace(".json", ""))] = data
    return profiles

def save_profile(profile: dict):
    os.makedirs(PROFILES_DIR, exist_ok=True)
    slug = profile["slug"]
    with open(os.path.join(PROFILES_DIR, f"{slug}.json"), "w", encoding="utf-8") as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)

def delete_profile(slug: str):
    path = os.path.join(PROFILES_DIR, f"{slug}.json")
    if os.path.exists(path):
        os.remove(path)


# ─── PDF / LANGDOCK ──────────────────────────────────────────────────────────

def extract_text_from_pdf(uploaded_file) -> str:
    with pdfplumber.open(uploaded_file) as pdf:
        text = ""
        for page in pdf.pages:
            text += (page.extract_text() or "") + "\n"
    return text.strip()


def parse_ci_with_langdock(pdf_text: str) -> dict:
    prompt = f"""Hier ist der Text aus einer Corporate Identity / Brand Guidelines PDF.
Extrahiere alle relevanten Informationen und gib sie als valides JSON zurück – kein Text davor oder danach, nur JSON.

Das JSON muss exakt diese Struktur haben:
{{
  "name": "Firmenname",
  "industry": "Branche",
  "slogan": "Slogan oder Claim",
  "website": "URL falls gefunden",
  "target_audience": "Zielgruppe(n) falls beschrieben",
  "tone": "Du (locker) / Du (professionell) / Sie (formell) / Mix",
  "values": "Markenwerte, USPs",
  "language": "Deutsch / Englisch / Deutsch + Englisch",
  "colors": [
    {{"name": "Primär", "hex": "#XXXXXX"}},
    {{"name": "Sekundär", "hex": "#XXXXXX"}},
    {{"name": "Akzent", "hex": "#XXXXXX"}}
  ],
  "font": "Schriftart(en)",
  "social": {{
    "instagram": "@handle oder leer",
    "tiktok": "@handle oder leer",
    "linkedin": "Name/URL oder leer",
    "youtube": "Name/URL oder leer"
  }},
  "notes": "Weitere relevante Hinweise für Content-Erstellung (Bildsprache, Do's & Don'ts, Hashtags etc.)"
}}

Falls eine Information nicht im PDF steht, lass das Feld leer ("").
Falls Farben als RGB oder CMYK angegeben sind, konvertiere sie zu HEX.
Falls mehr als 3 Farben definiert sind, wähle die 3 wichtigsten.

PDF-Text:
{pdf_text[:8000]}"""

    # Try Langdock first, fall back to Claude
    raw_text = ""
    if LANGDOCK_API_KEY and LANGDOCK_AGENT_ID:
        try:
            headers = {
                "Authorization": f"Bearer {LANGDOCK_API_KEY}",
                "Content-Type": "application/json"
            }
            payload = {
                "agentId": LANGDOCK_AGENT_ID,
                "messages": [{"id": "msg-1", "role": "user", "parts": [{"type": "text", "text": prompt}]}],
                "stream": False
            }
            response = requests.post(LANGDOCK_URL, headers=headers, json=payload, timeout=120)
            response.raise_for_status()
            data = response.json()
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
        except Exception as e:
            print(f"  Langdock Fehler: {e}")

    if not raw_text:
        try:
            anthropic_key = get_secret("ANTHROPIC_API_KEY")
            if anthropic_key:
                import anthropic
                client = anthropic.Anthropic(api_key=anthropic_key)
                resp = client.messages.create(
                    model="claude-sonnet-4-6",
                    max_tokens=4096,
                    messages=[{"role": "user", "content": prompt}]
                )
                for block in resp.content:
                    if block.type == "text":
                        raw_text = block.text.strip()
        except Exception as e:
            print(f"  Claude Fehler: {e}")

    if not raw_text:
        return None

    try:
        if "```" in raw_text:
            raw_text = raw_text.split("```")[1]
            if raw_text.startswith("json"):
                raw_text = raw_text[4:]
        return json.loads(raw_text.strip())
    except json.JSONDecodeError:
        return None
