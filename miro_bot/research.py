"""
Research module for Miro Konzept Bot — scrapes TikTok, Meta Ads, news & trends
before generating concepts.
"""
import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()


def _secret(key: str, default: str = "") -> str:
    try:
        import streamlit as st
        return st.secrets[key]
    except Exception:
        return os.getenv(key, default)


APIFY_API_TOKEN = _secret("APIFY_API_TOKEN")
APIFY_TIKTOK_ACTOR = "clockworks~tiktok-scraper"
APIFY_GOOGLE_ACTOR = "nFJndFXA5zjCTuudP"
APIFY_META_ADS_ACTOR = "easyapi~facebook-ads-library-scraper"
LANGDOCK_API_KEY = _secret("LANGDOCK_API_KEY")
LANGDOCK_AGENT_ID = _secret("LANGDOCK_AGENT_ID")
LANGDOCK_URL = "https://api.langdock.com/agent/v1/chat/completions"


# ─── TIKTOK TRENDS ────────────────────────────────────────────────────────

def scrape_tiktok(queries: list, max_per_query: int = 5) -> list:
    """Scrape TikTok for trending videos matching the queries."""
    if not APIFY_API_TOKEN:
        return []

    run_url = (
        f"https://api.apify.com/v2/acts/{APIFY_TIKTOK_ACTOR}/runs"
        f"?token={APIFY_API_TOKEN}&waitForFinish=120"
    )
    payload = {
        "searchQueries": queries,
        "resultsPerPage": max_per_query,
        "searchSection": "/video",
    }

    try:
        resp = requests.post(run_url, json=payload, timeout=130)
        resp.raise_for_status()
        dataset_id = resp.json()["data"]["defaultDatasetId"]

        items_url = (
            f"https://api.apify.com/v2/datasets/{dataset_id}/items"
            f"?token={APIFY_API_TOKEN}&limit={max_per_query * len(queries)}"
        )
        items = requests.get(items_url, timeout=30).json()

        results = []
        for item in items:
            url = item.get("webVideoUrl", "")
            if not url:
                continue
            results.append({
                "url": url,
                "description": (item.get("text", "") or "")[:200],
                "author": item.get("authorMeta", {}).get("name", "?"),
                "views": item.get("playCount", 0),
                "likes": item.get("diggCount", 0),
                "platform": "TikTok",
            })
        return results
    except Exception as e:
        print(f"  TikTok Scrape Fehler: {e}")
        return []


# ─── META ADS LIBRARY ─────────────────────────────────────────────────────

def scrape_meta_ads(query: str, max_results: int = 10) -> list:
    """Search the actual Meta Ads Library via Apify for active ads.

    Uses easyapi/facebook-ads-library-scraper to query the real Meta Ad Library.
    Returns ad text, page name, CTA, format, and platforms.
    """
    if not APIFY_API_TOKEN:
        return []

    run_url = (
        f"https://api.apify.com/v2/acts/{APIFY_META_ADS_ACTOR}/runs"
        f"?token={APIFY_API_TOKEN}&waitForFinish=90"
    )
    payload = {
        "search_query": query,
        "country": "DE",
        "ad_type": "all",
        "active_status": "active",
        "max_ads": max_results,
    }

    try:
        resp = requests.post(run_url, json=payload, timeout=100)
        resp.raise_for_status()
        dataset_id = resp.json()["data"]["defaultDatasetId"]

        items_url = (
            f"https://api.apify.com/v2/datasets/{dataset_id}/items"
            f"?token={APIFY_API_TOKEN}&limit={max_results}"
        )
        items = requests.get(items_url, timeout=30).json()

        results = []
        for item in items:
            snapshot = item.get("snapshot", {})
            if isinstance(snapshot, str):
                continue

            page_name = item.get("page_name", "") or snapshot.get("page_name", "")
            body = snapshot.get("body", {})
            ad_text = body.get("text", "") if isinstance(body, dict) else str(body)
            cta = snapshot.get("cta_text", "")
            display_format = snapshot.get("display_format", "")
            platforms = item.get("publisher_platform", [])
            link = snapshot.get("link_url", "")

            if not ad_text and not page_name:
                continue

            results.append({
                "page_name": page_name,
                "ad_text": ad_text[:300],
                "cta": cta,
                "format": display_format,
                "platforms": platforms,
                "link": str(link)[:200] if link else "",
                "platform": "Meta Ads Library",
            })

        return results[:max_results]
    except Exception as e:
        print(f"  Meta Ads Library Fehler: {e}")
        return []


# ─── NEWS & BRANCHENTRENDS ────────────────────────────────────────────────

def scrape_news(industry: str, extra_query: str = "") -> list:
    """Scrape recent industry news via Google Search."""
    if not APIFY_API_TOKEN:
        return []

    queries = f"{industry} Trends 2026\n{industry} aktuelle Entwicklungen"
    if extra_query:
        queries += f"\n{extra_query}"

    run_url = (
        f"https://api.apify.com/v2/acts/{APIFY_GOOGLE_ACTOR}/runs"
        f"?token={APIFY_API_TOKEN}&waitForFinish=120"
    )
    payload = {
        "queries": queries,
        "maxPagesPerQuery": 1,
        "resultsPerPage": 5,
        "languageCode": "de",
        "countryCode": "de",
    }

    try:
        resp = requests.post(run_url, json=payload, timeout=130)
        resp.raise_for_status()
        dataset_id = resp.json()["data"]["defaultDatasetId"]

        items_url = (
            f"https://api.apify.com/v2/datasets/{dataset_id}/items"
            f"?token={APIFY_API_TOKEN}&limit=20"
        )
        items = requests.get(items_url, timeout=30).json()

        results = []
        for item in items:
            for r in item.get("organicResults", []):
                if len(results) >= 8:
                    break
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "snippet": r.get("description", "")[:200],
                })
        return results[:8]
    except Exception as e:
        print(f"  News Scrape Fehler: {e}")
        return []


# ─── FULL RESEARCH ────────────────────────────────────────────────────────

def run_research(industry: str, video_themen: list,
                 profile: dict = None, progress_callback=None) -> dict:
    """Run full research: TikTok trends, Meta Ads, industry news.

    Returns dict with all research data.
    """
    def update(pct, text):
        if progress_callback:
            progress_callback(min(pct, 1.0), text)

    client_name = profile.get("name", "") if profile else ""

    # TikTok: industry trends + video-specific queries
    update(0.1, "TikTok Trends scrapen...")
    tiktok_queries = [f"{industry} trends", f"{industry} video marketing"]
    for thema in video_themen[:3]:
        if thema.strip():
            tiktok_queries.append(thema)
    tiktok_results = scrape_tiktok(tiktok_queries, max_per_query=5)

    # Meta Ads
    update(0.4, "Meta Ads Library durchsuchen...")
    meta_results = scrape_meta_ads(industry)

    # News
    update(0.7, "Branchentrends & News scrapen...")
    news_results = scrape_news(industry, client_name)

    update(1.0, "Research abgeschlossen!")

    return {
        "tiktok": tiktok_results,
        "meta_ads": meta_results,
        "news": news_results,
    }


# ─── GENERATE VIDEO IDEAS ────────────────────────────────────────────────

def generate_video_ideas(research: dict, video_themen: list,
                         profile: dict = None, kontext: str = "",
                         file_text: str = "") -> list:
    """Use Merlin to generate short video ideas based on research + themen.

    Returns list of dicts: [{video_num, thema, idea_title, idea_summary, inspiration}]
    """
    import re

    if not LANGDOCK_API_KEY or not LANGDOCK_AGENT_ID:
        raise RuntimeError("LANGDOCK_API_KEY oder LANGDOCK_AGENT_ID nicht konfiguriert")

    profile_block = ""
    if profile:
        parts = []
        for key, label in [("name", "Kunde"), ("industry", "Branche"),
                           ("target_audience", "Zielgruppe"), ("tone", "Tonalität")]:
            if profile.get(key):
                parts.append(f"{label}: {profile[key]}")
        if parts:
            profile_block = "\n".join(parts)

    # Summarize research
    tiktok_summary = ""
    for t in research.get("tiktok", [])[:8]:
        tiktok_summary += f"- {t['description'][:100]} ({t['views']:,} Views)\n"

    meta_summary = ""
    for m in research.get("meta_ads", [])[:5]:
        page = m.get("page_name", "?")
        text = m.get("ad_text", "")[:100]
        fmt = m.get("format", "")
        meta_summary += f"- {page} ({fmt}): {text}\n"

    news_summary = ""
    for n in research.get("news", [])[:5]:
        news_summary += f"- {n['title'][:80]}\n"

    themen_list = ""
    for i, thema in enumerate(video_themen):
        if thema.strip():
            themen_list += f"Video {i+1}: {thema}\n"

    file_block = f"Dokument-Inhalt:\n{file_text[:4000]}" if file_text else ""

    prompt = f"""Du bist Creative Director bei einer Videoagentur. Basierend auf dem Research erstelle kurze Video-Ideen.

{profile_block}

{f"Kontext: {kontext}" if kontext else ""}
{file_block}

=== RESEARCH ERGEBNISSE ===

TikTok Trends (was gerade viral geht):
{tiktok_summary if tiktok_summary else "Keine TikTok-Daten verfügbar"}

Meta Ads (was Wettbewerber schalten):
{meta_summary if meta_summary else "Keine Meta Ads-Daten verfügbar"}

Branchennews & Trends:
{news_summary if news_summary else "Keine News verfügbar"}

=== VIDEOS ===
{themen_list}

Erstelle für JEDES Video eine kurze Idee mit:
- Arbeitstitel (knackig, 3-6 Worte)
- Kernidee (2-3 Sätze, was passiert im Video, welches Gefühl, welche Story)
- Inspiration (welcher Trend oder welche Referenz hat die Idee inspiriert)

REGELN:
- Natürlich und menschlich formulieren
- Keine Gedankenstriche, keine Bulletpoints
- Kreativ und konkret, nicht generisch

Antworte NUR mit validem JSON Array:
[
    {{
        "video_num": 1,
        "thema": "Originalthema",
        "idea_title": "Kurzer Arbeitstitel",
        "idea_summary": "2-3 Sätze Kernidee",
        "inspiration": "Welcher Trend/Referenz inspiriert das"
    }}
]

NUR JSON, kein Markdown."""

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

        try:
            import anthropic
            client = anthropic.Anthropic(api_key=_secret("ANTHROPIC_API_KEY"))
            fix_resp = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=4096,
                messages=[{"role": "user", "content": f"Fix this broken JSON array and return ONLY valid JSON:\n\n{raw_text[:4000]}"}],
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
