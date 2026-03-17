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


def enrich_leads_with_emails(leads: list) -> list:
    """Visit each lead's website and scrape email from Impressum/Kontakt pages.

    Uses Apify web scraper to crawl the lead websites and extract emails.
    Only enriches leads that have a website but no email.
    """
    import re

    leads_needing_email = [l for l in leads if l.get("website") and not l.get("email")]
    if not leads_needing_email or not APIFY_API_TOKEN:
        return leads

    # Collect website URLs — try /impressum and /kontakt paths
    start_urls = []
    for lead in leads_needing_email:
        base = lead["website"].rstrip("/")
        start_urls.append({"url": base})
        start_urls.append({"url": f"{base}/impressum"})
        start_urls.append({"url": f"{base}/kontakt"})
        start_urls.append({"url": f"{base}/contact"})

    # Cap at 100 URLs to avoid excessive costs
    start_urls = start_urls[:100]

    run_url = (
        f"https://api.apify.com/v2/acts/{WEB_SCRAPER_ACTOR}/runs"
        f"?token={APIFY_API_TOKEN}&waitForFinish=300"
    )
    payload = {
        "startUrls": start_urls,
        "maxCrawlPages": len(start_urls),
        "maxCrawlDepth": 0,
    }

    try:
        print(f"  Email-Enrichment: {len(leads_needing_email)} Websites besuchen...")
        response = requests.post(run_url, json=payload, timeout=360)
        response.raise_for_status()

        run_data = response.json()
        dataset_id = run_data["data"]["defaultDatasetId"]

        items_url = (
            f"https://api.apify.com/v2/datasets/{dataset_id}/items"
            f"?token={APIFY_API_TOKEN}&limit={len(start_urls)}"
        )
        items_resp = requests.get(items_url, timeout=60)
        items_resp.raise_for_status()
        items = items_resp.json()

        # Build map: domain → emails found
        email_pattern = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
        domain_emails = {}

        for item in items:
            text = item.get("text", "") or ""
            url = item.get("url", "") or ""

            emails = email_pattern.findall(text)
            # Filter junk emails
            emails = [e for e in emails if not any(
                x in e.lower() for x in [
                    "@example", "@test", "noreply", "@sentry", "@wixpress",
                    "@google", "@facebook", "@instagram", "@twitter",
                    ".png", ".jpg", ".gif", "@2x",
                ]
            )]

            if emails:
                # Extract domain from URL
                try:
                    from urllib.parse import urlparse
                    domain = urlparse(url).netloc.lower().replace("www.", "")
                    if domain not in domain_emails:
                        domain_emails[domain] = emails[0]
                except Exception:
                    pass

        # Match emails back to leads
        enriched = 0
        for lead in leads:
            if lead.get("email"):
                continue
            website = lead.get("website", "")
            if not website:
                continue
            try:
                from urllib.parse import urlparse
                domain = urlparse(website).netloc.lower().replace("www.", "")
                if domain in domain_emails:
                    lead["email"] = domain_emails[domain]
                    enriched += 1
            except Exception:
                pass

        print(f"  Email-Enrichment: {enriched} Emails gefunden")

    except Exception as e:
        print(f"  Email-Enrichment Fehler: {e}")

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
