"""
Lead Scraper — Scrape contact data, dedup against ClickUp, push new leads.
"""
import streamlit as st
from shared import inject_css

st.set_page_config(page_title="Lead Scraper", page_icon="🔍", layout="wide")
inject_css()

st.markdown("""
<div style="text-align:center; padding: 20px 0;">
    <div style="font-size:36px; font-weight:800;">🔍 Lead Scraper</div>
    <p style="color:#888; font-size:14px;">Kontaktdaten scrapen, mit ClickUp abgleichen, neue Leads pushen.</p>
</div>
""", unsafe_allow_html=True)

st.markdown("---")

# ─── CHECK APIFY KEY ──────────────────────────────────────────────────────

APIFY_API_TOKEN = ""
try:
    from lead_scraper.scraper import APIFY_API_TOKEN
except Exception:
    pass

if not APIFY_API_TOKEN:
    st.error("⚠️ `APIFY_API_TOKEN` nicht konfiguriert. Bitte in `.env` oder Streamlit Secrets setzen.")

# ─── SEARCH CONFIG ─────────────────────────────────────────────────────────

st.markdown('<div class="section-label">⚙️ Konfiguration</div>', unsafe_allow_html=True)

search_term = st.text_input(
    "Suchbegriff",
    placeholder="z.B. Hochzeitslocation, Eventlocation, Fotostudio...",
)
max_results = st.slider("Max. Ergebnisse", min_value=10, max_value=300, value=50, step=10)

st.markdown("<br>", unsafe_allow_html=True)

# ─── SCRAPE BUTTON ─────────────────────────────────────────────────────────

if st.button("🚀 Leads scrapen", use_container_width=True, type="primary",
             disabled=(not search_term or not APIFY_API_TOKEN)):
    from lead_scraper.scraper import scrape_google_maps, scrape_google_search, _fetch_page_text, _extract_emails_from_html

    # Step 1: Google Maps
    with st.spinner(f"🔍 Google Maps Scrape für '{search_term}'..."):
        try:
            leads = scrape_google_maps(search_term, max_results)
        except Exception as e:
            st.error(f"Google Maps Scraping fehlgeschlagen: {e}")
            leads = []

    gm_count = len(leads)
    st.info(f"📍 Google Maps: {gm_count} Leads gefunden")

    # Step 2: Google Search (finds businesses not on Maps)
    with st.spinner(f"🌐 Google Suche für '{search_term}'..."):
        try:
            gs_leads = scrape_google_search(search_term, max_results)
        except Exception as e:
            st.error(f"Google Suche fehlgeschlagen: {e}")
            gs_leads = []

    # Merge and deduplicate
    all_leads = leads + gs_leads
    seen = set()
    leads = []
    for lead in all_leads:
        key = lead["name"].lower().strip()
        if key not in seen:
            seen.add(key)
            leads.append(lead)

    # Also dedup by domain
    by_domain = {}
    for lead in leads:
        from urllib.parse import urlparse
        w = lead.get("website", "").rstrip("/").lower()
        if w:
            domain = urlparse(w if w.startswith("http") else f"https://{w}").netloc.lstrip("www.")
        else:
            domain = lead["name"].lower()
        if domain in by_domain:
            existing = by_domain[domain]
            if not existing.get("email") and lead.get("email"):
                by_domain[domain] = lead
        else:
            by_domain[domain] = lead
    leads = list(by_domain.values())

    if len(gs_leads) > 0:
        st.info(f"🌐 Google Suche: {len(gs_leads)} zusätzliche Leads → **{len(leads)} unique Leads** nach Deduplizierung")

    if not leads:
        st.warning("Keine Leads gefunden. Versuche einen anderen Suchbegriff.")
    else:
        n_with_website = sum(1 for l in leads if l.get("website"))
        n_without_email = sum(1 for l in leads if l.get("website") and not l.get("email"))
        st.info(f"📍 {len(leads)} Leads von Google Maps ({n_with_website} mit Website, {n_without_email} ohne Email)")

        # Step 2: Email Enrichment with progress
        if n_without_email > 0:
            progress_bar = st.progress(0, text="📧 Emails von Websites extrahieren...")
            leads_to_enrich = [l for l in leads if l.get("website") and not l.get("email")]
            enriched_count = 0
            failed_sites = []

            paths_to_try = ["", "/impressum", "/kontakt", "/contact", "/about", "/ueber-uns"]

            for idx, lead in enumerate(leads_to_enrich):
                base = lead["website"].rstrip("/")
                if not base.startswith("http"):
                    base = f"https://{base}"

                progress_bar.progress(
                    (idx + 1) / len(leads_to_enrich),
                    text=f"📧 ({idx+1}/{len(leads_to_enrich)}) {lead['name'][:40]}..."
                )

                found = False
                for path in paths_to_try:
                    url = f"{base}{path}"
                    html = _fetch_page_text(url)
                    if html:
                        emails = _extract_emails_from_html(html)
                        if emails:
                            lead["email"] = emails[0]
                            enriched_count += 1
                            found = True
                            break

                if not found:
                    failed_sites.append(lead["name"])

            progress_bar.empty()
            st.success(
                f"✅ {len(leads)} Leads gefunden! "
                f"({enriched_count + sum(1 for l in leads if l.get('email') and l not in leads_to_enrich)} mit E-Mail)"
            )

            if failed_sites and len(failed_sites) <= 10:
                with st.expander(f"⚠️ {len(failed_sites)} Leads ohne Email"):
                    for name in failed_sites:
                        st.caption(f"  — {name}")
        else:
            n_with_email = sum(1 for l in leads if l.get("email"))
            st.success(f"✅ {len(leads)} Leads gefunden! ({n_with_email} mit E-Mail)")

        st.session_state["scraped_leads"] = leads
        st.session_state["new_leads"] = leads
        st.session_state["duplicate_leads"] = []

st.markdown("---")

# ─── RESULTS ───────────────────────────────────────────────────────────────

new_leads = st.session_state.get("new_leads", [])
duplicate_leads = st.session_state.get("duplicate_leads", [])

if new_leads or duplicate_leads:

    # ─── CLICKUP SECTION (only shown when leads exist) ─────────────────────
    try:
        from lead_scraper.clickup import CLICKUP_API_KEY
    except Exception:
        CLICKUP_API_KEY = ""

    if CLICKUP_API_KEY and not st.session_state.get("clickup_dedup_done"):
        st.markdown('<div class="section-label">📋 ClickUp Abgleich</div>', unsafe_allow_html=True)

        # Step 1: Load spaces (only on button click, cached in session_state)
        if "clickup_spaces" not in st.session_state:
            if st.button("🔄 ClickUp laden", use_container_width=True):
                with st.spinner("⏳ ClickUp Spaces werden geladen... (kann einige Sekunden dauern)"):
                    try:
                        from lead_scraper.clickup import get_workspaces, get_spaces
                        workspaces = get_workspaces()
                        spaces = []
                        for ws in workspaces:
                            try:
                                for s in get_spaces(ws["id"]):
                                    spaces.append({"id": s["id"], "name": s["name"]})
                            except Exception:
                                pass
                        st.session_state["clickup_spaces"] = spaces
                        st.rerun()
                    except Exception as e:
                        st.error(f"ClickUp Fehler: {e}")

        if "clickup_spaces" in st.session_state:
            spaces = st.session_state["clickup_spaces"]
            if not spaces:
                st.warning("Keine ClickUp Spaces gefunden.")
            else:
                space_options = {s["name"]: s["id"] for s in spaces}
                selected_space = st.selectbox("ClickUp Space", options=list(space_options.keys()))
                space_id = space_options.get(selected_space, "")

                # Step 2: Load lists for selected space
                if space_id:
                    lists_key = f"clickup_lists_{space_id}"
                    if lists_key not in st.session_state:
                        with st.spinner("⏳ Listen werden geladen..."):
                            try:
                                from lead_scraper.clickup import get_folders, get_lists
                                folder_lists = []
                                try:
                                    for l in get_lists(space_id=space_id):
                                        folder_lists.append({"id": l["id"], "name": l["name"], "folder": "(ohne Ordner)"})
                                except Exception:
                                    pass
                                try:
                                    for folder in get_folders(space_id):
                                        try:
                                            for l in get_lists(folder_id=folder["id"]):
                                                folder_lists.append({"id": l["id"], "name": l["name"], "folder": folder["name"]})
                                        except Exception:
                                            pass
                                except Exception:
                                    pass
                                st.session_state[lists_key] = folder_lists
                            except Exception as e:
                                st.error(f"Fehler beim Laden der Listen: {e}")
                                st.session_state[lists_key] = []

                    folder_lists = st.session_state.get(lists_key, [])
                    if folder_lists:
                        list_options = {
                            f"{fl['folder']} / {fl['name']}": fl["id"]
                            for fl in folder_lists
                        }
                        selected_list = st.selectbox("ClickUp Liste", options=list(list_options.keys()))
                        clickup_list_id = list_options.get(selected_list, "")

                        if clickup_list_id:
                            if st.button("🔄 Mit ClickUp abgleichen", use_container_width=True):
                                try:
                                    from lead_scraper.clickup import dedup_leads, auto_detect_field_mapping

                                    with st.spinner("🔄 Abgleich mit ClickUp..."):
                                        result = dedup_leads(new_leads, clickup_list_id)
                                        st.session_state["new_leads"] = result["new"]
                                        st.session_state["duplicate_leads"] = result["duplicates"]
                                        st.session_state["clickup_existing"] = result["total_existing"]
                                        st.session_state["clickup_list_id"] = clickup_list_id
                                        st.session_state["clickup_dedup_done"] = True

                                        try:
                                            mapping = auto_detect_field_mapping(clickup_list_id)
                                            st.session_state["clickup_field_mapping"] = mapping
                                        except Exception:
                                            pass

                                    st.rerun()
                                except Exception as e:
                                    st.error(f"ClickUp Abgleich fehlgeschlagen: {e}")
                    elif folder_lists is not None:
                        st.info("Keine Listen in diesem Space gefunden.")

        st.markdown("---")

    # Refresh after possible dedup
    new_leads = st.session_state.get("new_leads", [])
    duplicate_leads = st.session_state.get("duplicate_leads", [])

    # Show dedup stats if available
    if st.session_state.get("clickup_dedup_done"):
        n_new = len(new_leads)
        n_dup = len(duplicate_leads)
        total_ex = st.session_state.get("clickup_existing", 0)
        st.info(f"📊 **{n_new} neue Leads** | {n_dup} Duplikate (bereits in ClickUp: {total_ex})")

    tab_new, tab_dup = st.tabs([
        f"✅ Neue Leads ({len(new_leads)})",
        f"🔄 Duplikate ({len(duplicate_leads)})"
    ])

    with tab_new:
        if new_leads:
            # Push to ClickUp button
            if CLICKUP_API_KEY and st.session_state.get("clickup_list_id"):
                if st.button("📤 Alle neuen Leads in ClickUp eintragen", type="primary",
                             use_container_width=True):
                    try:
                        from lead_scraper.clickup import push_leads_to_clickup
                        mapping = st.session_state.get("clickup_field_mapping", {})
                        list_id = st.session_state["clickup_list_id"]

                        with st.spinner(f"📤 {len(new_leads)} Leads in ClickUp eintragen..."):
                            result = push_leads_to_clickup(new_leads, list_id, mapping)

                        if result["created"] > 0:
                            st.success(f"✅ {result['created']} Leads erfolgreich eingetragen!")
                        if result["failed"] > 0:
                            st.warning(f"⚠️ {result['failed']} fehlgeschlagen")
                            for err in result["errors"][:5]:
                                st.caption(f"  ❌ {err}")
                    except Exception as e:
                        st.error(f"ClickUp Import fehlgeschlagen: {e}")

            # Display leads
            for i, lead in enumerate(new_leads):
                email = lead.get("email", "")
                phone = lead.get("phone", "")
                website = lead.get("website", "")

                email_display = f'<a href="mailto:{email}" style="color:#4fa3e0;">{email}</a>' if email else '<span style="color:#666;">—</span>'
                website_display = f'<a href="{website}" target="_blank" style="color:#4fa3e0;">{website[:40]}...</a>' if website else '<span style="color:#666;">—</span>'

                st.markdown(
                    f'<div style="background:#1e1e1e;border:1px solid #2a2a2a;border-radius:12px;'
                    f'padding:16px;margin-bottom:8px;">'
                    f'<div style="display:flex;justify-content:space-between;align-items:center;">'
                    f'<div style="font-size:16px;font-weight:700;">{lead["name"]}</div>'
                    f'<span style="background:#2ecc7120;color:#2ecc71;padding:2px 10px;'
                    f'border-radius:12px;font-size:11px;">NEU</span>'
                    f'</div>'
                    f'<div style="display:flex;gap:20px;margin-top:8px;flex-wrap:wrap;font-size:13px;">'
                    f'<span>📧 {email_display}</span>'
                    f'<span>📞 {phone if phone else "—"}</span>'
                    f'<span>🌐 {website_display}</span>'
                    f'</div>'
                    f'<div style="font-size:11px;color:#555;margin-top:6px;">'
                    f'Quelle: {lead.get("source", "—")} · Suche: {lead.get("search_term", "—")}'
                    f'</div>'
                    f'</div>',
                    unsafe_allow_html=True
                )
        else:
            st.info("Alle gefundenen Leads sind bereits in ClickUp vorhanden.")

    with tab_dup:
        if duplicate_leads:
            for lead in duplicate_leads:
                st.markdown(
                    f'<div style="background:#1e1e1e;border:1px solid #f39c1240;border-radius:12px;'
                    f'padding:16px;margin-bottom:8px;">'
                    f'<div style="display:flex;justify-content:space-between;align-items:center;">'
                    f'<div style="font-size:16px;font-weight:700;color:#888;">{lead["name"]}</div>'
                    f'<span style="background:#f39c1220;color:#f39c12;padding:2px 10px;'
                    f'border-radius:12px;font-size:11px;">DUPLIKAT</span>'
                    f'</div>'
                    f'<div style="font-size:13px;color:#666;margin-top:6px;">'
                    f'📧 {lead.get("email", "—")} · 📞 {lead.get("phone", "—")}'
                    f'</div>'
                    f'</div>',
                    unsafe_allow_html=True
                )
        else:
            st.info("Keine Duplikate gefunden.")

elif not st.session_state.get("scraped_leads"):
    st.markdown(
        '<div style="text-align:center;color:#555;padding:40px;">'
        '🔍 Gib einen Suchbegriff ein und klicke "Leads scrapen"'
        '</div>',
        unsafe_allow_html=True
    )

st.markdown("<br><br>", unsafe_allow_html=True)
