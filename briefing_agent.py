import os
import json
import hashlib
import time
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()


def _secret(key: str, default: str = "") -> str:
    """Get secret from st.secrets (Cloud) or os.environ (.env local)."""
    try:
        import streamlit as st
        return st.secrets[key]
    except Exception:
        return os.getenv(key, default)


ANTHROPIC_API_KEY = _secret("ANTHROPIC_API_KEY")
TAVILY_API_KEY = _secret("TAVILY_API_KEY")
APIFY_API_TOKEN = _secret("APIFY_API_TOKEN")
SUPABASE_URL = _secret("SUPABASE_URL")
SUPABASE_KEY = _secret("SUPABASE_KEY")


# ─── SUPABASE CLIENT ─────────────────────────────────────────────────────────

def get_supabase():
    from supabase import create_client
    return create_client(SUPABASE_URL, SUPABASE_KEY)


# ─── TOOL IMPLEMENTATIONS ────────────────────────────────────────────────────

def _scrape_trends(industry: str, region: str = "DE", platforms: list = None) -> dict:
    """Scrapes trends from Tavily (news), pytrends (Google Trends), and optionally Apify (social)."""
    results = {"news": [], "google_trends": [], "social": []}

    # 1. Tavily News Search
    if TAVILY_API_KEY:
        try:
            from tavily import TavilyClient
            tavily = TavilyClient(api_key=TAVILY_API_KEY)
            search = tavily.search(
                query=f"{industry} trends news Deutschland 2026",
                search_depth="advanced",
                max_results=8,
                include_answer=True,
            )
            for r in search.get("results", []):
                results["news"].append({
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "snippet": r.get("content", "")[:300],
                    "score": r.get("score", 0),
                })
            if search.get("answer"):
                results["news_summary"] = search["answer"]
        except Exception as e:
            results["news_error"] = str(e)

    # 2. Google Trends via pytrends
    try:
        from pytrends.request import TrendReq
        pytrends = TrendReq(hl="de-DE", tz=360)
        pytrends.build_payload([industry], cat=0, timeframe="now 7-d", geo=region)
        related = pytrends.related_queries()
        if industry in related:
            top = related[industry].get("top")
            rising = related[industry].get("rising")
            if top is not None and not top.empty:
                results["google_trends"].extend(
                    top.head(10).to_dict("records")
                )
            if rising is not None and not rising.empty:
                results["google_trends"].extend(
                    [{"query": r["query"], "value": r["value"], "type": "rising"}
                     for _, r in rising.head(5).iterrows()]
                )
    except Exception as e:
        results["google_trends_error"] = str(e)

    # 3. Apify Social Scraping (TikTok trending)
    if APIFY_API_TOKEN and platforms:
        import requests as req
        for platform in platforms[:2]:
            if platform.lower() in ("tiktok", "instagram"):
                try:
                    actor = "clockworks~tiktok-scraper" if platform.lower() == "tiktok" else "apify~instagram-scraper"
                    run_url = f"https://api.apify.com/v2/acts/{actor}/runs?token={APIFY_API_TOKEN}&waitForFinish=60"
                    payload = {"searchQueries": [industry], "resultsPerPage": 5, "searchSection": "/video"}
                    resp = req.post(run_url, json=payload, timeout=70)
                    if resp.status_code == 200:
                        dataset_id = resp.json().get("data", {}).get("defaultDatasetId")
                        if dataset_id:
                            items_url = f"https://api.apify.com/v2/datasets/{dataset_id}/items?token={APIFY_API_TOKEN}&limit=5"
                            items = req.get(items_url, timeout=30).json()
                            for item in items[:5]:
                                results["social"].append({
                                    "platform": platform,
                                    "text": (item.get("text", "") or "")[:200],
                                    "views": item.get("playCount", 0),
                                    "likes": item.get("diggCount", 0),
                                    "author": item.get("authorMeta", {}).get("name", "?"),
                                })
                except Exception as e:
                    results[f"{platform}_error"] = str(e)

    return results


def _get_posting_history(profile_slug: str, limit: int = 50) -> list:
    """Gets recent postings from Supabase for duplicate detection."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return []
    try:
        sb = get_supabase()
        resp = sb.table("postings").select("*").eq("profile_slug", profile_slug).order("created_at", desc=True).limit(limit).execute()
        return resp.data or []
    except Exception as e:
        return [{"error": str(e)}]


def _check_duplicate(title: str, profile_slug: str) -> dict:
    """Checks if a similar briefing already exists using simple text similarity."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return {"is_duplicate": False, "reason": "No database configured"}
    try:
        sb = get_supabase()
        # Get existing briefings for this profile
        resp = sb.table("briefings").select("titel, trend_quelle").eq("profile_slug", profile_slug).execute()
        existing = resp.data or []

        # Simple similarity check via normalized words
        title_words = set(title.lower().split())
        for item in existing:
            existing_words = set(item.get("titel", "").lower().split())
            if not title_words or not existing_words:
                continue
            overlap = len(title_words & existing_words) / max(len(title_words | existing_words), 1)
            if overlap > 0.6:
                return {
                    "is_duplicate": True,
                    "similar_to": item.get("titel", ""),
                    "overlap": round(overlap, 2),
                }
        return {"is_duplicate": False}
    except Exception as e:
        return {"is_duplicate": False, "error": str(e)}


def _save_briefing(briefing: dict, profile_slug: str) -> dict:
    """Saves a briefing to Supabase as draft."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return {"saved": False, "reason": "No database configured"}
    try:
        sb = get_supabase()
        row = {
            "profile_slug": profile_slug,
            "status": "draft",
            "created_at": datetime.now().isoformat(),
            **briefing,
        }
        resp = sb.table("briefings").insert(row).execute()
        return {"saved": True, "id": resp.data[0]["id"] if resp.data else None}
    except Exception as e:
        return {"saved": False, "error": str(e)}


# ─── TOOL DEFINITIONS FOR CLAUDE ─────────────────────────────────────────────

TOOLS = [
    {
        "name": "scrape_trends",
        "description": "Recherchiert aktuelle Trends und News für eine Branche. Nutzt Tavily (News), Google Trends und optional Apify (Social Media). Gibt strukturierte Trend-Daten zurück.",
        "input_schema": {
            "type": "object",
            "properties": {
                "industry": {"type": "string", "description": "Branche/Themengebiet, z.B. 'Social Media Marketing', 'Fitness', 'E-Commerce'"},
                "region": {"type": "string", "description": "ISO Region Code, z.B. 'DE' für Deutschland", "default": "DE"},
                "platforms": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Social Media Plattformen zum Scrapen, z.B. ['TikTok', 'Instagram']"
                },
            },
            "required": ["industry"],
        },
    },
    {
        "name": "get_posting_history",
        "description": "Lädt die bisherigen Postings eines Kundenprofils aus der Datenbank, um Duplikate zu vermeiden und auf bestehende Inhalte aufzubauen.",
        "input_schema": {
            "type": "object",
            "properties": {
                "profile_slug": {"type": "string", "description": "Slug des Kundenprofils"},
                "limit": {"type": "integer", "description": "Maximale Anzahl an Postings", "default": 50},
            },
            "required": ["profile_slug"],
        },
    },
    {
        "name": "check_duplicate",
        "description": "Prüft ob ein Briefing-Titel bereits existiert oder zu ähnlich zu bestehenden Briefings ist. Verhindert doppelte Inhalte.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Titel des geplanten Briefings"},
                "profile_slug": {"type": "string", "description": "Slug des Kundenprofils"},
            },
            "required": ["title", "profile_slug"],
        },
    },
    {
        "name": "save_briefing",
        "description": "Speichert ein fertiges Briefing als Draft in der Datenbank.",
        "input_schema": {
            "type": "object",
            "properties": {
                "briefing": {
                    "type": "object",
                    "description": "Das vollständige Briefing-Objekt mit allen Feldern (titel, trend_quelle, relevanz_score, format, zielgruppe, hook, slide_struktur, ton, farben, caption_idee, hashtags, best_post_time, was_vermeiden)",
                },
                "profile_slug": {"type": "string", "description": "Slug des Kundenprofils"},
            },
            "required": ["briefing", "profile_slug"],
        },
    },
]


# ─── TOOL EXECUTOR ────────────────────────────────────────────────────────────

def execute_tool(name: str, input_data: dict) -> str:
    """Executes a tool by name and returns the JSON result."""
    if name == "scrape_trends":
        result = _scrape_trends(
            industry=input_data["industry"],
            region=input_data.get("region", "DE"),
            platforms=input_data.get("platforms"),
        )
    elif name == "get_posting_history":
        result = _get_posting_history(
            profile_slug=input_data["profile_slug"],
            limit=input_data.get("limit", 50),
        )
    elif name == "check_duplicate":
        result = _check_duplicate(
            title=input_data["title"],
            profile_slug=input_data["profile_slug"],
        )
    elif name == "save_briefing":
        result = _save_briefing(
            briefing=input_data["briefing"],
            profile_slug=input_data["profile_slug"],
        )
    else:
        result = {"error": f"Unknown tool: {name}"}

    return json.dumps(result, ensure_ascii=False, default=str)


# ─── BRIEFING AGENT ──────────────────────────────────────────────────────────

def run_briefing_agent(
    profile: dict,
    num_briefings: int = 5,
    focus: str = "",
    platforms: list = None,
    on_status=None,
) -> list:
    """
    Runs the Briefing Agent using Claude API with Tool Use.
    Returns a list of generated briefings.

    Args:
        profile: Customer profile dict (from load_profiles())
        num_briefings: Number of briefings to generate
        focus: Optional focus topic/theme
        platforms: Target platforms (e.g. ["TikTok", "Instagram Reel"])
        on_status: Optional callback for status updates (str -> None)
    """
    import anthropic

    if not ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY nicht in .env konfiguriert.")

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    def status(msg):
        if on_status:
            on_status(msg)
        print(f"  [Agent] {msg}")

    # Build profile context
    colors_str = ", ".join([f"{c['name']}: {c['hex']}" for c in profile.get("colors", [])])
    social_str = ", ".join([f"{k}: {v}" for k, v in profile.get("social", {}).items() if v])
    platforms_str = ", ".join(platforms) if platforms else "TikTok, Instagram Reel, Instagram Post"

    focus_section = f"\nSPEZIALFOKUS: {focus}\n" if focus else ""

    system_prompt = f"""Du bist ein erfahrener Social Media Strategist und Content-Berater für die Agentur NIRO Media.
Deine Aufgabe: Erstelle {num_briefings} einzigartige, trendbasierte Content-Briefings für den Kunden.

KUNDENPROFIL:
- Firma: {profile.get('name', '')}
- Branche: {profile.get('industry', '')}
- Slogan: {profile.get('slogan', '')}
- Zielgruppe: {profile.get('target_audience', '')}
- Tonalität: {profile.get('tone', '')}
- Markenwerte: {profile.get('values', '')}
- Markenfarben: {colors_str}
- Sprache: {profile.get('language', 'Deutsch')}
- Social Media: {social_str}
- Hinweise: {profile.get('notes', '')}
{focus_section}
ZIELPLATTFORMEN: {platforms_str}

VORGEHEN:
1. Nutze scrape_trends um aktuelle Trends in der Branche "{profile.get('industry', '')}" zu recherchieren
2. Nutze get_posting_history um bisherige Postings zu laden und Duplikate zu vermeiden
3. Für jeden Briefing-Entwurf: Nutze check_duplicate um sicherzustellen, dass der Titel einzigartig ist
4. Generiere {num_briefings} Briefings basierend auf den gefundenen Trends
5. Speichere jedes Briefing mit save_briefing

BRIEFING FORMAT (jedes Briefing muss ALLE diese Felder haben):
- titel: Arbeitstitel des Posts (kurz, prägnant)
- trend_quelle: Woher der Trend stammt (z.B. "Google Trends", "TikTok Viral", "Branchennews")
- relevanz_score: 1-10 wie relevant der Trend für den Kunden ist
- format: Videoformat (z.B. "Talking Head", "B-Roll Montage", "Tutorial", "POV", "Listicle")
- zielgruppe: Spezifische Zielgruppe für diesen Post
- hook: Der erste Satz / Hook der Aufmerksamkeit fängt
- slide_struktur: Array mit Slide/Shot-Beschreibungen für das Video
- ton: Tonalität des Posts (z.B. "informativ & locker", "provokant", "emotional")
- farben: Farbpalette basierend auf CI des Kunden
- caption_idee: Fertige Caption mit Emojis
- hashtags: Array relevanter Hashtags
- best_post_time: Optimale Posting-Zeit
- was_vermeiden: Was bei diesem Post vermieden werden sollte

WICHTIG:
- Jedes Briefing muss auf einem echten, aktuellen Trend basieren
- Keine generischen Ideen – alles muss datengetrieben sein
- Hooks müssen scroll-stopping sein
- Captions müssen ready-to-post sein
- Passe Tonalität und Stil an die Kundenmarke an
- Vermeide Duplikate zu bestehenden Postings"""

    messages = [
        {
            "role": "user",
            "content": f"Erstelle {num_briefings} trendbasierte Content-Briefings für {profile.get('name', 'den Kunden')}. Recherchiere zuerst aktuelle Trends, prüfe auf Duplikate, und speichere die fertigen Briefings."
        }
    ]

    status("Agent gestartet – recherchiere Trends...")

    # Agentic loop
    all_briefings = []
    max_iterations = 20

    for iteration in range(max_iterations):
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=8192,
            system=system_prompt,
            tools=TOOLS,
            messages=messages,
        )

        # If Claude is done
        if response.stop_reason == "end_turn":
            # Extract final text
            for block in response.content:
                if block.type == "text" and block.text:
                    status("Agent fertig.")
            break

        # Extract tool calls
        tool_use_blocks = [b for b in response.content if b.type == "tool_use"]

        if not tool_use_blocks:
            break

        # Append assistant response
        messages.append({"role": "assistant", "content": response.content})

        # Execute tools and collect results
        tool_results = []
        for tool in tool_use_blocks:
            status(f"Tool: {tool.name}...")
            result = execute_tool(tool.name, tool.input)

            # Track saved briefings
            if tool.name == "save_briefing":
                try:
                    parsed = json.loads(result)
                    if parsed.get("saved"):
                        all_briefings.append(tool.input.get("briefing", {}))
                except Exception:
                    pass

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool.id,
                "content": result,
            })

        messages.append({"role": "user", "content": tool_results})

    # If no briefings saved to DB, try to extract from the conversation
    if not all_briefings:
        status("Extrahiere Briefings aus Agent-Antwort...")
        for msg in messages:
            if isinstance(msg.get("content"), list):
                for block in msg["content"]:
                    if hasattr(block, "type") and block.type == "tool_use" and block.name == "save_briefing":
                        briefing = block.input.get("briefing", {})
                        if briefing:
                            all_briefings.append(briefing)

    # Also save locally as backup
    os.makedirs("outputs/briefings", exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    local_path = f"outputs/briefings/{profile.get('slug', 'unknown')}_{timestamp}.json"
    with open(local_path, "w", encoding="utf-8") as f:
        json.dump({
            "profile": profile.get("slug", ""),
            "client": profile.get("name", ""),
            "generated_at": timestamp,
            "num_briefings": len(all_briefings),
            "briefings": all_briefings,
        }, f, ensure_ascii=False, indent=2)

    status(f"{len(all_briefings)} Briefings generiert → {local_path}")
    return all_briefings


# ─── LOAD SAVED BRIEFINGS ────────────────────────────────────────────────────

def load_all_briefing_files() -> list:
    """Returns list of saved briefing filenames."""
    path = "outputs/briefings"
    if not os.path.exists(path):
        return []
    files = [f for f in os.listdir(path) if f.endswith(".json")]
    return sorted(files, reverse=True)


def load_briefing_file(filename: str) -> dict:
    """Loads a briefing file by name."""
    path = os.path.join("outputs/briefings", filename)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None
