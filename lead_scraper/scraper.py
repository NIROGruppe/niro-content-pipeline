"""
Lead Scraper — finds business contact data via Apify (Google Maps + Web Scraper).
Generic: works for any industry/search term.
"""
import os
import time
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

# Apify actor IDs
GOOGLE_MAPS_ACTOR = "nwua9Gu5YrADL7ZDj"  # compass/crawler-google-places
WEB_SCRAPER_ACTOR = "moJRLRc85AitArpNN"  # apify/website-content-crawler

# Regions to auto-expand a search term into
DEFAULT_REGIONS = [
    "Deutschland", "NRW", "Bayern", "Baden-Württemberg", "Hessen",
    "Berlin", "Hamburg", "München", "Köln", "Frankfurt", "Düsseldorf",
    "Stuttgart", "Leipzig", "Dresden", "Hannover",
]


def scrape_google_maps(search_term: str, max_results: int = 100,
                       regions: list = None) -> list:
    """Scrape Google Maps for business listings via Apify.

    Automatically expands search_term with location keywords.
    Returns list of dicts with: name, email, phone, website, address.
    """
    if not APIFY_API_TOKEN:
        raise RuntimeError("APIFY_API_TOKEN nicht konfiguriert")

    if regions is None:
        regions = DEFAULT_REGIONS[:8]  # Top 8 regions

    # Build search queries: "Hochzeitslocation NRW", "Hochzeitslocation Bayern", etc.
    queries = [f"{search_term} {region}" for region in regions]

    run_url = f"https://api.apify.com/v2/acts/{GOOGLE_MAPS_ACTOR}/runs?token={APIFY_API_TOKEN}&waitForFinish=300"
    payload = {
        "searchStringsArray": queries,
        "maxCrawledPlacesPerSearch": max(max_results // len(queries), 5),
        "language": "de",
        "maxImages": 0,
        "maxReviews": 0,
        "onlyDataFromSearchPage": False,
    }

    print(f"  Google Maps: {len(queries)} Suchanfragen starten...")
    response = requests.post(run_url, json=payload, timeout=360)
    response.raise_for_status()

    run_data = response.json()
    dataset_id = run_data["data"]["defaultDatasetId"]

    # Fetch results
    items_url = (
        f"https://api.apify.com/v2/datasets/{dataset_id}/items"
        f"?token={APIFY_API_TOKEN}&limit={max_results}"
    )
    items_resp = requests.get(items_url, timeout=60)
    items_resp.raise_for_status()
    items = items_resp.json()

    leads = []
    seen_names = set()

    for item in items:
        name = (item.get("title") or item.get("name") or "").strip()
        if not name or name.lower() in seen_names:
            continue
        seen_names.add(name.lower())

        # Extract email from various fields
        email = ""
        if item.get("email"):
            email = item["email"]
        elif item.get("emails") and isinstance(item["emails"], list):
            email = item["emails"][0] if item["emails"] else ""

        phone = item.get("phone") or item.get("phoneUnformatted") or ""
        website = item.get("website") or item.get("url") or ""
        address = item.get("address") or item.get("street") or ""

        leads.append({
            "name": name,
            "email": email,
            "phone": phone,
            "website": website,
            "address": address,
            "source": "Google Maps",
            "search_term": search_term,
        })

    print(f"  Google Maps: {len(leads)} Leads gefunden")
    return leads


def scrape_web_directories(search_term: str, max_results: int = 50) -> list:
    """Scrape web directories/portals for contact data via Apify web scraper.

    Searches common business directories for the given term.
    Returns list of dicts with: name, email, phone, website.
    """
    if not APIFY_API_TOKEN:
        return []

    # Search URLs for common German business directories
    search_urls = [
        f"https://www.google.com/search?q={search_term}+email+kontakt+site:hochzeitsportal24.de",
        f"https://www.google.com/search?q={search_term}+email+kontakt+site:eventlocation.de",
        f"https://www.google.com/search?q={search_term}+kontakt+email",
    ]

    run_url = f"https://api.apify.com/v2/acts/{WEB_SCRAPER_ACTOR}/runs?token={APIFY_API_TOKEN}&waitForFinish=180"
    payload = {
        "startUrls": [{"url": u} for u in search_urls],
        "maxCrawlPages": max_results,
        "maxCrawlDepth": 1,
    }

    try:
        print(f"  Web Scraper: Verzeichnisse durchsuchen...")
        response = requests.post(run_url, json=payload, timeout=240)
        response.raise_for_status()

        run_data = response.json()
        dataset_id = run_data["data"]["defaultDatasetId"]

        items_url = (
            f"https://api.apify.com/v2/datasets/{dataset_id}/items"
            f"?token={APIFY_API_TOKEN}&limit={max_results}"
        )
        items_resp = requests.get(items_url, timeout=60)
        items_resp.raise_for_status()
        items = items_resp.json()

        # Extract contact info from crawled pages
        import re
        email_pattern = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
        phone_pattern = re.compile(r'(?:\+49|0049|0)\s*[\d\s/\-()]{8,15}')

        leads = []
        for item in items:
            text = item.get("text", "") or ""
            title = item.get("title", "") or ""
            url = item.get("url", "") or ""

            emails = email_pattern.findall(text)
            phones = phone_pattern.findall(text)

            # Filter out generic emails
            emails = [e for e in emails if not any(
                x in e.lower() for x in ["@example", "@test", "noreply", "info@google"]
            )]

            if emails:
                leads.append({
                    "name": title[:100] if title else url,
                    "email": emails[0],
                    "phone": phones[0].strip() if phones else "",
                    "website": url,
                    "address": "",
                    "source": "Web Scraper",
                    "search_term": search_term,
                })

        print(f"  Web Scraper: {len(leads)} Leads gefunden")
        return leads

    except Exception as e:
        print(f"  Web Scraper Fehler: {e}")
        return []


def _fetch_page_text(url: str, timeout: int = 10) -> str:
    """Fetch a single page and return its HTML text. Returns '' on failure."""
    try:
        resp = requests.get(
            url,
            timeout=timeout,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                              "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
            },
            allow_redirects=True,
        )
        resp.raise_for_status()
        return resp.text
    except Exception:
        return ""


def _extract_emails_from_html(html: str) -> list:
    """Extract email addresses from HTML, decode obfuscated ones too."""
    import re
    from html import unescape

    # Decode HTML entities first (e.g. &#64; → @, &#046; → .)
    html = unescape(html)

    # Also handle [at] [dot] obfuscation
    deobfuscated = html.replace("[at]", "@").replace("[AT]", "@")
    deobfuscated = deobfuscated.replace("[dot]", ".").replace("[DOT]", ".")
    deobfuscated = deobfuscated.replace(" (at) ", "@").replace(" [at] ", "@")
    deobfuscated = deobfuscated.replace(" (dot) ", ".").replace(" [dot] ", ".")

    # Find mailto: links (most reliable)
    mailto_pattern = re.compile(r'mailto:([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})')
    emails = mailto_pattern.findall(deobfuscated)

    # Also find plain emails in text
    email_pattern = re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}')
    emails.extend(email_pattern.findall(deobfuscated))

    # Filter junk
    junk = [
        "@example", "@test", "noreply", "@sentry", "@wixpress",
        "@google", "@facebook", "@instagram", "@twitter", "@youtube",
        ".png", ".jpg", ".gif", ".svg", ".webp", "@2x", "@3x",
        "schema.org", "w3.org", "wix.com", "wordpress",
    ]
    clean = []
    seen = set()
    for e in emails:
        e_lower = e.lower().strip()
        if e_lower in seen:
            continue
        if any(x in e_lower for x in junk):
            continue
        seen.add(e_lower)
        clean.append(e)

    return clean


def enrich_leads_with_emails(leads: list) -> list:
    """Visit each lead's website directly and scrape email from homepage/Impressum/Kontakt.

    Uses direct HTTP requests (no Apify) — fast and free.
    Only enriches leads that have a website but no email.
    """
    from urllib.parse import urlparse

    leads_needing_email = [l for l in leads if l.get("website") and not l.get("email")]
    if not leads_needing_email:
        return leads

    print(f"  Email-Enrichment: {len(leads_needing_email)} Websites direkt besuchen...")

    # Paths to check on each website
    paths_to_try = ["", "/impressum", "/kontakt", "/contact", "/about", "/ueber-uns"]

    enriched = 0
    for lead in leads_needing_email:
        base = lead["website"].rstrip("/")

        # Make sure URL has a scheme
        if not base.startswith("http"):
            base = f"https://{base}"

        found_email = None
        for path in paths_to_try:
            url = f"{base}{path}"
            html = _fetch_page_text(url)
            if not html:
                continue

            emails = _extract_emails_from_html(html)
            if emails:
                found_email = emails[0]
                break

        if found_email:
            lead["email"] = found_email
            enriched += 1
            print(f"    ✓ {lead['name']}: {found_email}")

    print(f"  Email-Enrichment: {enriched}/{len(leads_needing_email)} Emails gefunden")
    return leads


def run_full_scrape(search_term: str, max_results: int = 100) -> list:
    """Run full scrape: Google Maps + Web directories + email enrichment."""
    all_leads = []

    # 1. Google Maps (primary)
    try:
        gm_leads = scrape_google_maps(search_term, max_results)
        all_leads.extend(gm_leads)
    except Exception as e:
        print(f"  Google Maps Fehler: {e}")

    # 2. Web directories (secondary)
    try:
        web_leads = scrape_web_directories(search_term, max_results=30)
        all_leads.extend(web_leads)
    except Exception as e:
        print(f"  Web Scraper Fehler: {e}")

    # Deduplicate by name (case-insensitive)
    seen = set()
    unique = []
    for lead in all_leads:
        key = lead["name"].lower().strip()
        if key not in seen:
            seen.add(key)
            unique.append(lead)

    # Merge: if same website found from both sources, prefer the one with email
    by_website = {}
    for lead in unique:
        w = lead.get("website", "").rstrip("/").lower()
        if w and w in by_website:
            existing = by_website[w]
            if not existing.get("email") and lead.get("email"):
                by_website[w] = lead
        elif w:
            by_website[w] = lead
        else:
            by_website[lead["name"]] = lead

    final = list(by_website.values())

    # 3. Email enrichment — visit websites of leads without email
    try:
        final = enrich_leads_with_emails(final)
    except Exception as e:
        print(f"  Email-Enrichment Fehler: {e}")

    print(f"  Gesamt: {len(final)} einzigartige Leads")
    return final
