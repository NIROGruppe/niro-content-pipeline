import streamlit as st
import os
from datetime import datetime
from shared import (
    inject_css, load_profiles, save_profile, delete_profile,
    extract_text_from_pdf, parse_ci_with_langdock
)

LOGOS_DIR = "data/profiles/logos"


def save_logo(slug: str, uploaded_file) -> str:
    """Saves an uploaded logo file and returns the path."""
    os.makedirs(LOGOS_DIR, exist_ok=True)
    ext = uploaded_file.name.rsplit(".", 1)[-1].lower() if "." in uploaded_file.name else "png"
    logo_path = os.path.join(LOGOS_DIR, f"{slug}.{ext}")
    with open(logo_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return logo_path

st.set_page_config(page_title="Kundenprofile", page_icon="👤", layout="wide")
inject_css()

st.markdown("# 👤 Kundenprofile")
st.markdown("Corporate Identities anlegen und verwalten.")
st.markdown("---")

profiles = load_profiles()

# ─── PDF IMPORT ──────────────────────────────────────────────────────────────
with st.expander("📄 Profil aus CI-PDF erstellen", expanded=False):
    uploaded_pdf = st.file_uploader("Corporate Identity PDF hochladen", type=["pdf"], key="ci_pdf")

    if uploaded_pdf and st.button("PDF analysieren", use_container_width=True):
        with st.spinner("PDF wird gelesen und analysiert..."):
            pdf_text = extract_text_from_pdf(uploaded_pdf)
            if not pdf_text:
                st.error("Konnte keinen Text aus der PDF extrahieren.")
            else:
                st.caption(f"{len(pdf_text)} Zeichen extrahiert")
                parsed = parse_ci_with_langdock(pdf_text)
                if parsed:
                    st.session_state["pdf_profile_draft"] = parsed
                    st.success("CI erfolgreich extrahiert! Bitte unten prüfen und anpassen.")
                else:
                    st.error("Konnte kein strukturiertes Profil aus der PDF extrahieren.")

    if "pdf_profile_draft" in st.session_state:
        draft = st.session_state["pdf_profile_draft"]
        st.markdown("---")
        st.markdown("##### Extrahiertes Profil – bitte prüfen und anpassen")

        with st.form("pdf_profile_form"):
            st.markdown("##### Allgemein")
            col_a, col_b = st.columns(2)
            with col_a:
                pdf_name = st.text_input("Firmenname *", value=draft.get("name", ""), key="pdf_name")
                pdf_industry = st.text_input("Branche", value=draft.get("industry", ""), key="pdf_industry")
            with col_b:
                pdf_slogan = st.text_input("Slogan / Claim", value=draft.get("slogan", ""), key="pdf_slogan")
                pdf_website = st.text_input("Website", value=draft.get("website", ""), key="pdf_website")

            st.markdown("##### Zielgruppe & Tonalität")
            col_c, col_d = st.columns(2)
            tone_options = ["Du (locker)", "Du (professionell)", "Sie (formell)", "Mix"]
            tone_idx = tone_options.index(draft.get("tone", "Du (locker)")) if draft.get("tone") in tone_options else 0
            with col_c:
                pdf_target = st.text_area("Zielgruppe", value=draft.get("target_audience", ""), key="pdf_target")
                pdf_tone = st.selectbox("Tonalität", tone_options, index=tone_idx, key="pdf_tone")
            with col_d:
                pdf_values = st.text_area("Markenwerte / USPs", value=draft.get("values", ""), key="pdf_values")
                lang_options = ["Deutsch", "Englisch", "Deutsch + Englisch"]
                lang_idx = lang_options.index(draft.get("language", "Deutsch")) if draft.get("language") in lang_options else 0
                pdf_lang = st.selectbox("Sprache", lang_options, index=lang_idx, key="pdf_lang")

            st.markdown("##### Corporate Design")
            draft_colors = draft.get("colors", [{"name": "Primär", "hex": "#e63946"}, {"name": "Sekundär", "hex": "#1a1a2e"}, {"name": "Akzent", "hex": "#f4a261"}])
            while len(draft_colors) < 3:
                draft_colors.append({"name": "", "hex": "#333333"})
            col_e, col_f, col_g = st.columns(3)
            with col_e:
                pdf_c1 = st.color_picker("Primärfarbe", value=draft_colors[0].get("hex", "#e63946"), key="pdf_c1")
                pdf_c1n = st.text_input("Name Primärfarbe", value=draft_colors[0].get("name", "Primär"), key="pdf_c1n")
            with col_f:
                pdf_c2 = st.color_picker("Sekundärfarbe", value=draft_colors[1].get("hex", "#1a1a2e"), key="pdf_c2")
                pdf_c2n = st.text_input("Name Sekundärfarbe", value=draft_colors[1].get("name", "Sekundär"), key="pdf_c2n")
            with col_g:
                pdf_c3 = st.color_picker("Akzentfarbe", value=draft_colors[2].get("hex", "#f4a261"), key="pdf_c3")
                pdf_c3n = st.text_input("Name Akzentfarbe", value=draft_colors[2].get("name", "Akzent"), key="pdf_c3n")

            pdf_font = st.text_input("Schriftart(en)", value=draft.get("font", ""), key="pdf_font")

            st.markdown("##### Social Media")
            draft_social = draft.get("social", {})
            col_h, col_i = st.columns(2)
            with col_h:
                pdf_insta = st.text_input("Instagram", value=draft_social.get("instagram", ""), key="pdf_insta")
                pdf_tiktok = st.text_input("TikTok", value=draft_social.get("tiktok", ""), key="pdf_tiktok")
            with col_i:
                pdf_linkedin = st.text_input("LinkedIn", value=draft_social.get("linkedin", ""), key="pdf_linkedin")
                pdf_youtube = st.text_input("YouTube", value=draft_social.get("youtube", ""), key="pdf_youtube")

            st.markdown("##### Logo")
            pdf_logo = st.file_uploader("Logo hochladen", type=["png", "jpg", "jpeg", "svg", "webp"], key="pdf_logo")

            st.markdown("##### Zusätzliche Hinweise")
            pdf_notes = st.text_area("Notizen", value=draft.get("notes", ""), key="pdf_notes")

            col_save, col_discard = st.columns(2)
            with col_save:
                pdf_submitted = st.form_submit_button("Profil speichern", use_container_width=True)
            with col_discard:
                pdf_discarded = st.form_submit_button("Verwerfen", use_container_width=True)

            if pdf_submitted and pdf_name:
                slug = pdf_name.lower().replace(" ", "_").replace("-", "_")
                slug = "".join(c for c in slug if c.isalnum() or c == "_")
                logo_path = ""
                if pdf_logo:
                    logo_path = save_logo(slug, pdf_logo)
                profile = {
                    "slug": slug,
                    "name": pdf_name,
                    "industry": pdf_industry,
                    "slogan": pdf_slogan,
                    "website": pdf_website,
                    "target_audience": pdf_target,
                    "tone": pdf_tone,
                    "values": pdf_values,
                    "language": pdf_lang,
                    "colors": [
                        {"name": pdf_c1n, "hex": pdf_c1},
                        {"name": pdf_c2n, "hex": pdf_c2},
                        {"name": pdf_c3n, "hex": pdf_c3},
                    ],
                    "font": pdf_font,
                    "logo": logo_path,
                    "social": {"instagram": pdf_insta, "tiktok": pdf_tiktok, "linkedin": pdf_linkedin, "youtube": pdf_youtube},
                    "notes": pdf_notes,
                    "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                }
                save_profile(profile)
                del st.session_state["pdf_profile_draft"]
                st.success(f"Profil **{pdf_name}** gespeichert!")
                st.rerun()
            elif pdf_submitted:
                st.error("Bitte Firmennamen angeben.")
            elif pdf_discarded:
                del st.session_state["pdf_profile_draft"]
                st.rerun()


# ─── NEUES PROFIL MANUELL ────────────────────────────────────────────────────
with st.expander("➕ Neues Profil manuell erstellen", expanded=not bool(profiles) and "pdf_profile_draft" not in st.session_state):
    with st.form("new_profile", clear_on_submit=True):
        st.markdown("##### Allgemein")
        col_a, col_b = st.columns(2)
        with col_a:
            p_name = st.text_input("Firmenname *")
            p_industry = st.text_input("Branche", placeholder="z.B. Seniorenheim, Autohaus, Gastronomie")
        with col_b:
            p_slogan = st.text_input("Slogan / Claim")
            p_website = st.text_input("Website", placeholder="https://...")

        st.markdown("##### Zielgruppe & Tonalität")
        col_c, col_d = st.columns(2)
        with col_c:
            p_target = st.text_area("Zielgruppe", placeholder="z.B. Pflegekräfte 25-45, Quereinsteiger, Berufsanfänger")
            p_tone = st.selectbox("Tonalität", ["Du (locker)", "Du (professionell)", "Sie (formell)", "Mix"])
        with col_d:
            p_values = st.text_area("Markenwerte / USPs", placeholder="z.B. Familiengeführt, Nachhaltig, Innovativ")
            p_lang = st.selectbox("Sprache", ["Deutsch", "Englisch", "Deutsch + Englisch"])

        st.markdown("##### Corporate Design")
        col_e, col_f, col_g = st.columns(3)
        with col_e:
            p_color1 = st.color_picker("Primärfarbe", "#e63946")
            p_color1_name = st.text_input("Name Primärfarbe", value="Primär")
        with col_f:
            p_color2 = st.color_picker("Sekundärfarbe", "#1a1a2e")
            p_color2_name = st.text_input("Name Sekundärfarbe", value="Sekundär")
        with col_g:
            p_color3 = st.color_picker("Akzentfarbe", "#f4a261")
            p_color3_name = st.text_input("Name Akzentfarbe", value="Akzent")

        p_font = st.text_input("Schriftart(en)", placeholder="z.B. Montserrat, Open Sans")

        st.markdown("##### Logo")
        p_logo = st.file_uploader("Logo hochladen", type=["png", "jpg", "jpeg", "svg", "webp"], key="manual_logo")

        st.markdown("##### Social Media")
        col_h, col_i = st.columns(2)
        with col_h:
            p_insta = st.text_input("Instagram", placeholder="@handle")
            p_tiktok = st.text_input("TikTok", placeholder="@handle")
        with col_i:
            p_linkedin = st.text_input("LinkedIn", placeholder="Firmenname oder URL")
            p_youtube = st.text_input("YouTube", placeholder="Kanalname oder URL")

        st.markdown("##### Zusätzliche Hinweise")
        p_notes = st.text_area("Notizen für Content-Erstellung", placeholder="z.B. Bestimmte Themen vermeiden, bestimmte Hashtags immer nutzen, Bildsprache-Vorgaben...")

        submitted = st.form_submit_button("Profil speichern", use_container_width=True)

        if submitted and p_name:
            slug = p_name.lower().replace(" ", "_").replace("-", "_")
            slug = "".join(c for c in slug if c.isalnum() or c == "_")
            logo_path = ""
            if p_logo:
                logo_path = save_logo(slug, p_logo)
            profile = {
                "slug": slug,
                "name": p_name,
                "industry": p_industry,
                "slogan": p_slogan,
                "website": p_website,
                "target_audience": p_target,
                "tone": p_tone,
                "values": p_values,
                "language": p_lang,
                "colors": [
                    {"name": p_color1_name, "hex": p_color1},
                    {"name": p_color2_name, "hex": p_color2},
                    {"name": p_color3_name, "hex": p_color3},
                ],
                "font": p_font,
                "logo": logo_path,
                "social": {
                    "instagram": p_insta,
                    "tiktok": p_tiktok,
                    "linkedin": p_linkedin,
                    "youtube": p_youtube,
                },
                "notes": p_notes,
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            }
            save_profile(profile)
            st.success(f"Profil **{p_name}** gespeichert!")
            st.rerun()
        elif submitted:
            st.error("Bitte Firmennamen angeben.")


# ─── BESTEHENDE PROFILE ─────────────────────────────────────────────────────
if profiles:
    st.markdown("### Gespeicherte Profile")

    for slug, prof in sorted(profiles.items(), key=lambda x: x[1].get("name", "")):
        colors_html = ""
        for c in prof.get("colors", []):
            colors_html += f'<div style="display:inline-block;width:24px;height:24px;background:{c["hex"]};border-radius:6px;border:2px solid #333;margin-right:4px;" title="{c["name"]} ({c["hex"]})"></div>'

        with st.expander(f"**{prof['name']}** — {prof.get('industry', '')}"):

            # Toggle between view and edit mode
            edit_key = f"edit_mode_{slug}"
            if edit_key not in st.session_state:
                st.session_state[edit_key] = False

            if not st.session_state[edit_key]:
                # ── VIEW MODE ──
                col1, col2 = st.columns([2, 1])
                with col1:
                    st.markdown(f"**Branche:** {prof.get('industry', '–')}")
                    st.markdown(f"**Slogan:** {prof.get('slogan', '–')}")
                    st.markdown(f"**Website:** {prof.get('website', '–')}")
                    st.markdown(f"**Zielgruppe:** {prof.get('target_audience', '–')}")
                    st.markdown(f"**Tonalität:** {prof.get('tone', '–')}")
                    st.markdown(f"**Werte/USPs:** {prof.get('values', '–')}")
                    if prof.get("notes"):
                        st.info(f"📋 {prof['notes']}")
                with col2:
                    logo_path = prof.get("logo", "")
                    if logo_path and os.path.exists(logo_path):
                        st.image(logo_path, width=120)
                    st.markdown('<div class="section-label">Farben</div>', unsafe_allow_html=True)
                    st.markdown(colors_html, unsafe_allow_html=True)
                    st.markdown(f"**Schrift:** {prof.get('font', '–')}")
                    st.markdown("---")
                    social = prof.get("social", {})
                    for platform, handle in social.items():
                        if handle:
                            st.markdown(f"**{platform.capitalize()}:** {handle}")
                    st.markdown("---")
                    st.markdown(f"<div style='color:#555;font-size:11px;'>Erstellt: {prof.get('created_at', '–')}</div>", unsafe_allow_html=True)

                btn_col1, btn_col2 = st.columns(2)
                with btn_col1:
                    if st.button("✏️ Bearbeiten", key=f"btn_edit_{slug}", use_container_width=True):
                        st.session_state[edit_key] = True
                        st.rerun()
                with btn_col2:
                    if st.button("🗑️ Löschen", key=f"del_{slug}", use_container_width=True):
                        delete_profile(slug)
                        st.rerun()

            else:
                # ── EDIT MODE ──
                with st.form(f"edit_form_{slug}"):
                    st.markdown("##### Allgemein")
                    e_col_a, e_col_b = st.columns(2)
                    with e_col_a:
                        e_name = st.text_input("Firmenname *", value=prof.get("name", ""), key=f"e_name_{slug}")
                        e_industry = st.text_input("Branche", value=prof.get("industry", ""), key=f"e_industry_{slug}")
                    with e_col_b:
                        e_slogan = st.text_input("Slogan / Claim", value=prof.get("slogan", ""), key=f"e_slogan_{slug}")
                        e_website = st.text_input("Website", value=prof.get("website", ""), key=f"e_website_{slug}")

                    st.markdown("##### Zielgruppe & Tonalität")
                    e_col_c, e_col_d = st.columns(2)
                    tone_options = ["Du (locker)", "Du (professionell)", "Sie (formell)", "Mix"]
                    tone_idx = tone_options.index(prof.get("tone", "Du (locker)")) if prof.get("tone") in tone_options else 0
                    lang_options = ["Deutsch", "Englisch", "Deutsch + Englisch"]
                    lang_idx = lang_options.index(prof.get("language", "Deutsch")) if prof.get("language") in lang_options else 0
                    with e_col_c:
                        e_target = st.text_area("Zielgruppe", value=prof.get("target_audience", ""), key=f"e_target_{slug}")
                        e_tone = st.selectbox("Tonalität", tone_options, index=tone_idx, key=f"e_tone_{slug}")
                    with e_col_d:
                        e_values = st.text_area("Markenwerte / USPs", value=prof.get("values", ""), key=f"e_values_{slug}")
                        e_lang = st.selectbox("Sprache", lang_options, index=lang_idx, key=f"e_lang_{slug}")

                    st.markdown("##### Corporate Design")
                    existing_colors = prof.get("colors", [{"name": "Primär", "hex": "#e63946"}, {"name": "Sekundär", "hex": "#1a1a2e"}, {"name": "Akzent", "hex": "#f4a261"}])
                    while len(existing_colors) < 3:
                        existing_colors.append({"name": "", "hex": "#333333"})
                    e_col_e, e_col_f, e_col_g = st.columns(3)
                    with e_col_e:
                        e_c1 = st.color_picker("Primärfarbe", value=existing_colors[0].get("hex", "#e63946"), key=f"e_c1_{slug}")
                        e_c1n = st.text_input("Name Primärfarbe", value=existing_colors[0].get("name", "Primär"), key=f"e_c1n_{slug}")
                    with e_col_f:
                        e_c2 = st.color_picker("Sekundärfarbe", value=existing_colors[1].get("hex", "#1a1a2e"), key=f"e_c2_{slug}")
                        e_c2n = st.text_input("Name Sekundärfarbe", value=existing_colors[1].get("name", "Sekundär"), key=f"e_c2n_{slug}")
                    with e_col_g:
                        e_c3 = st.color_picker("Akzentfarbe", value=existing_colors[2].get("hex", "#f4a261"), key=f"e_c3_{slug}")
                        e_c3n = st.text_input("Name Akzentfarbe", value=existing_colors[2].get("name", "Akzent"), key=f"e_c3n_{slug}")

                    e_font = st.text_input("Schriftart(en)", value=prof.get("font", ""), key=f"e_font_{slug}")

                    st.markdown("##### Logo")
                    existing_logo = prof.get("logo", "")
                    if existing_logo and os.path.exists(existing_logo):
                        st.image(existing_logo, width=80)
                    e_logo = st.file_uploader("Logo ändern" if existing_logo else "Logo hochladen", type=["png", "jpg", "jpeg", "svg", "webp"], key=f"e_logo_{slug}")

                    st.markdown("##### Social Media")
                    existing_social = prof.get("social", {})
                    e_col_h, e_col_i = st.columns(2)
                    with e_col_h:
                        e_insta = st.text_input("Instagram", value=existing_social.get("instagram", ""), key=f"e_insta_{slug}")
                        e_tiktok = st.text_input("TikTok", value=existing_social.get("tiktok", ""), key=f"e_tiktok_{slug}")
                    with e_col_i:
                        e_linkedin = st.text_input("LinkedIn", value=existing_social.get("linkedin", ""), key=f"e_linkedin_{slug}")
                        e_youtube = st.text_input("YouTube", value=existing_social.get("youtube", ""), key=f"e_youtube_{slug}")

                    st.markdown("##### Zusätzliche Hinweise")
                    e_notes = st.text_area("Notizen", value=prof.get("notes", ""), key=f"e_notes_{slug}")

                    save_col, cancel_col = st.columns(2)
                    with save_col:
                        e_submitted = st.form_submit_button("💾 Speichern", use_container_width=True)
                    with cancel_col:
                        e_cancelled = st.form_submit_button("Abbrechen", use_container_width=True)

                    if e_submitted and e_name:
                        logo_path = existing_logo
                        if e_logo:
                            logo_path = save_logo(slug, e_logo)
                        updated_profile = {
                            "slug": slug,
                            "name": e_name,
                            "industry": e_industry,
                            "slogan": e_slogan,
                            "website": e_website,
                            "target_audience": e_target,
                            "tone": e_tone,
                            "values": e_values,
                            "language": e_lang,
                            "colors": [
                                {"name": e_c1n, "hex": e_c1},
                                {"name": e_c2n, "hex": e_c2},
                                {"name": e_c3n, "hex": e_c3},
                            ],
                            "font": e_font,
                            "logo": logo_path,
                            "social": {"instagram": e_insta, "tiktok": e_tiktok, "linkedin": e_linkedin, "youtube": e_youtube},
                            "notes": e_notes,
                            "created_at": prof.get("created_at", datetime.now().strftime("%Y-%m-%d %H:%M")),
                        }
                        save_profile(updated_profile)
                        st.session_state[edit_key] = False
                        st.success(f"Profil **{e_name}** aktualisiert!")
                        st.rerun()
                    elif e_submitted:
                        st.error("Bitte Firmennamen angeben.")
                    elif e_cancelled:
                        st.session_state[edit_key] = False
                        st.rerun()
else:
    st.info("Noch keine Profile vorhanden. Erstelle dein erstes Profil oben.")
