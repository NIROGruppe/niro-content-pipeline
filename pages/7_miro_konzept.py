"""
Miro Konzept Bot — Merlin generiert Konzepte, Bot platziert sie visuell auf Miro Boards.
Supports: Template-based (from template board) or freeform concept generation.
"""
import streamlit as st
from shared import inject_css, load_profiles, extract_text_from_pdf

st.set_page_config(page_title="Miro Konzept Bot", page_icon="🎨", layout="wide")
inject_css()

st.markdown("""
<div style="text-align:center; padding: 20px 0;">
    <div style="font-size:36px; font-weight:800;">🎨 Miro Konzept Bot</div>
    <p style="color:#888; font-size:14px;">Merlin erstellt Konzepte → automatisch visuell ins Miro Board</p>
</div>
""", unsafe_allow_html=True)

st.markdown("---")

# ─── CONFIG ───────────────────────────────────────────────────────────────

st.markdown('<div class="section-label">⚙️ Konfiguration</div>', unsafe_allow_html=True)

board_input = st.text_input(
    "Ziel Miro Board (URL oder ID)",
    placeholder="https://miro.com/app/board/uXjVK1234=/ oder Board-ID",
)

# Template selection
st.markdown('<div class="section-label">📐 Template</div>', unsafe_allow_html=True)

# Load templates from template board
if "miro_templates" not in st.session_state:
    st.session_state["miro_templates"] = None

if st.button("🔄 Templates laden", use_container_width=False):
    with st.spinner("Templates vom Template-Board laden..."):
        try:
            from miro_bot.template_bot import read_templates
            templates = read_templates()
            st.session_state["miro_templates"] = templates
            st.rerun()
        except Exception as e:
            st.error(f"Templates laden fehlgeschlagen: {e}")

templates = st.session_state.get("miro_templates")

if templates:
    template_names = list(templates.keys())
    selected_template = st.selectbox(
        "Template auswählen",
        options=template_names,
    )

    # Show template fields
    if selected_template and selected_template in templates:
        tpl = templates[selected_template]
        fields = tpl.get("fields", [])
        if fields:
            with st.expander(f"Felder im Template ({len(fields)})", expanded=False):
                for f in fields:
                    label = f.get("label", "Unbekannt")
                    color = f.get("fill_color", "")
                    st.caption(f"🔲 {label} ({color})")
        else:
            st.info("Keine leeren Felder im Template gefunden.")
else:
    st.info("Klicke 'Templates laden' um die verfügbaren Vorlagen zu sehen.")
    selected_template = None

# Customer Profile
profiles = load_profiles()
profile_options = {"(Kein Profil)": None}
profile_options.update({p.get("name", slug): p for slug, p in profiles.items()})

selected_profile_name = st.selectbox("Kundenprofil", options=list(profile_options.keys()))
selected_profile = profile_options[selected_profile_name]

if selected_profile:
    with st.expander(f"Profil: {selected_profile.get('name', '')}", expanded=False):
        cols = st.columns(3)
        with cols[0]:
            st.caption(f"**Branche:** {selected_profile.get('industry', '—')}")
            st.caption(f"**Tonalität:** {selected_profile.get('tone', '—')}")
        with cols[1]:
            st.caption(f"**Zielgruppe:** {selected_profile.get('target_audience', '—')}")
            st.caption(f"**Sprache:** {selected_profile.get('language', '—')}")
        with cols[2]:
            st.caption(f"**Werte:** {selected_profile.get('values', '—')}")

# Topic
thema = st.text_input(
    "Konzept-Thema / Briefing",
    placeholder="z.B. Employer Branding Video für Pflegekräfte-Recruiting...",
)

# File upload + Context
c3, c4 = st.columns(2)

with c3:
    uploaded_files = st.file_uploader(
        "Dateien (optional)",
        type=["pdf", "txt"],
        accept_multiple_files=True,
        help="z.B. Stellenanzeigen, Briefings, Referenzen",
    )

with c4:
    kontext = st.text_area(
        "Zusätzlicher Kontext (optional)",
        placeholder="Besondere Anforderungen, Ziele, Hinweise...",
        height=130,
    )

st.markdown("<br>", unsafe_allow_html=True)

# ─── GENERATE ─────────────────────────────────────────────────────────────

can_generate = board_input and thema and templates and selected_template

if st.button("🚀 Konzept erstellen & auf Board platzieren", use_container_width=True,
             type="primary", disabled=not can_generate):

    from miro_bot.miro_api import parse_board_id, MIRO_API_TOKEN
    from miro_bot.template_bot import generate_content_for_fields, place_template_on_board

    if not MIRO_API_TOKEN:
        st.error("⚠️ `MIRO_API_TOKEN` nicht konfiguriert.")
        st.stop()

    board_id = parse_board_id(board_input)
    tpl = templates[selected_template]
    fields = tpl.get("fields", [])

    # Extract text from uploaded files
    file_text = ""
    if uploaded_files:
        for uf in uploaded_files:
            if uf.name.endswith(".pdf"):
                try:
                    file_text += extract_text_from_pdf(uf) + "\n\n"
                except Exception:
                    file_text += f"[PDF {uf.name} konnte nicht gelesen werden]\n\n"
            elif uf.name.endswith(".txt"):
                file_text += uf.read().decode("utf-8", errors="ignore") + "\n\n"

    # Step 1: Generate content via Merlin
    with st.spinner(f"🧠 Merlin füllt {selected_template} aus..."):
        try:
            generated = generate_content_for_fields(
                fields=fields,
                thema=thema,
                template_name=selected_template,
                profile=selected_profile,
                kontext=kontext,
                file_text=file_text.strip(),
            )
        except Exception as e:
            st.error(f"Konzept-Generierung fehlgeschlagen: {e}")
            st.stop()

    # Show preview
    st.markdown("### 📋 Generierte Inhalte")
    for label, content in generated.items():
        with st.expander(label, expanded=True):
            st.write(content)

    st.markdown("---")

    # Step 2: Place on Miro board
    progress = st.progress(0, text="📐 Board wird vorbereitet...")

    try:
        result = place_template_on_board(
            target_board_id=board_id,
            template_name=selected_template,
            generated_content=generated,
            templates=templates,
            progress_callback=lambda pct, text: progress.progress(min(pct, 1.0), text=text),
        )

        progress.empty()
        st.success(
            f"✅ **{result['template_name']}** erfolgreich platziert! "
            f"({result['items_created']} Elemente, {result['fields_filled']} Felder gefüllt)"
        )
        st.markdown(
            f'<a href="{result["board_url"]}" target="_blank" '
            f'style="display:inline-block;background:#ffd02f;color:#1a1a2e;padding:12px 24px;'
            f'border-radius:8px;text-decoration:none;font-weight:700;margin-top:8px;">'
            f'🔗 Board öffnen</a>',
            unsafe_allow_html=True,
        )

    except Exception as e:
        progress.empty()
        st.error(f"Miro-Platzierung fehlgeschlagen: {e}")

st.markdown("<br><br>", unsafe_allow_html=True)
