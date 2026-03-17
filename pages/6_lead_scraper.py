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

# ─── CHECK API KEYS ────────────────────────────────────────────────────────

try:
    from lead_scraper.scraper import APIFY_API_TOKEN
except Exception:
    APIFY_API_TOKEN = ""

try:
    from lead_scraper.clickup import CLICKUP_API_KEY
except Exception:
    CLICKUP_API_KEY = ""

if not APIFY_API_TOKEN:
    st.error("⚠️ `APIFY_API_TOKEN` nicht konfiguriert. Bitte in `.env` oder Streamlit Secrets setzen.")
if not CLICKUP_API_KEY:
    st.warning("⚠️ `CLICKUP_API_KEY` nicht konfiguriert. Scraping funktioniert, aber kein ClickUp-Sync.")

# ─── CONFIGURATION ─────────────────────────────────────────────────────────

@st.cache_data(ttl=300, show_spinner=False)
def _load_clickup_lists():
    """Load all ClickUp lists (cached for 5 min)."""
    from lead_scraper.clickup import get_workspaces, get_spaces, get_folders, get_lists
    workspaces = get_workspaces()
    all_lists = []
    for ws in workspaces:
        try:
            spaces = get_spaces(ws["id"])
        except Exception:
            continue
        for space in spaces:
            try:
                fl_lists = get_lists(space_id=space["id"])
                for l in fl_lists:
                    all_lists.append({"id": l["id"], "name": f"{space['name']} / {l['name']}"})
            except Exception:
                pass
            try:
                folders = get_folders(space["id"])
                for folder in folders:
                    try:
                        f_lists = get_lists(folder_id=folder["id"])
                        for l in f_lists:
                            all_lists.append({
                                "id": l["id"],
                                "name": f"{space['name']} / {folder['name']} / {l['name']}"
                            })
                    except Exception:
                        pass
            except Exception:
                pass
    return all_lists


st.markdown('<div class="section-label">⚙️ Konfiguration</div>', unsafe_allow_html=True)

col1, col2 = st.columns(2)

with col1:
    search_term = st.text_input(
        "Suchbegriff",
        placeholder="z.B. Hochzeitslocation, Eventlocation, Fotostudio...",
    )
    max_results = st.slider("Max. Ergebnisse", min_value=10, max_value=300, value=50, step=10)

clickup_list_id = ""

with col2:
    if CLICKUP_API_KEY:
        try:
            lists = _load_clickup_lists()
            if lists:
                list_options = {l["name"]: l["id"] for l in lists}
                selected_list = st.selectbox("ClickUp Liste", options=list(list_options.keys()))
                clickup_list_id = list_options.get(selected_list, "")
            else:
                st.info("Keine ClickUp Listen gefunden.")
        except Exception as e:
            st.error(f"ClickUp Fehler: {e}")
            if st.button("🔄 Neu laden", key="reload_clickup"):
                _load_clickup_lists.clear()
                st.rerun()
    else:
        st.info("ClickUp nicht verbunden — Leads werden nur in der App angezeigt.")

st.markdown("<br>", unsafe_allow_html=True)

# ─── SCRAPE BUTTON ─────────────────────────────────────────────────────────

if st.button("🚀 Leads scrapen", use_container_width=True, type="primary",
             disabled=(not search_term or not APIFY_API_TOKEN)):
    from lead_scraper.scraper import run_full_scrape

    # Step 1: Scrape
    with st.spinner(f"🔍 Scrape läuft für '{search_term}'... (kann 2-5 Min. dauern)"):
        try:
            leads = run_full_scrape(search_term, max_results)
        except Exception as e:
            st.error(f"Scraping fehlgeschlagen: {e}")
            leads = []

    if not leads:
        st.warning("Keine Leads gefunden. Versuche einen anderen Suchbegriff.")
    else:
        st.success(f"✅ {len(leads)} Leads gefunden!")
        st.session_state["scraped_leads"] = leads
        st.session_state["new_leads"] = leads
        st.session_state["duplicate_leads"] = []

        # Step 2: ClickUp Dedup (only if connected)
        if clickup_list_id and CLICKUP_API_KEY:
            try:
                from lead_scraper.clickup import dedup_leads, auto_detect_field_mapping

                with st.spinner("🔄 Abgleich mit ClickUp..."):
                    result = dedup_leads(leads, clickup_list_id)
                    st.session_state["new_leads"] = result["new"]
                    st.session_state["duplicate_leads"] = result["duplicates"]
                    st.session_state["clickup_existing"] = result["total_existing"]
                    st.session_state["clickup_list_id"] = clickup_list_id

                    n_new = len(result["new"])
                    n_dup = len(result["duplicates"])
                    st.info(
                        f"📊 **{n_new} neue Leads** | {n_dup} Duplikate "
                        f"(bereits in ClickUp: {result['total_existing']})"
                    )

                    # Auto-detect field mapping
                    try:
                        mapping = auto_detect_field_mapping(clickup_list_id)
                        st.session_state["clickup_field_mapping"] = mapping
                    except Exception:
                        pass

            except Exception as e:
                st.error(f"ClickUp Abgleich fehlgeschlagen: {e}")

st.markdown("---")

# ─── RESULTS ───────────────────────────────────────────────────────────────

new_leads = st.session_state.get("new_leads", [])
duplicate_leads = st.session_state.get("duplicate_leads", [])

if new_leads or duplicate_leads:
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
