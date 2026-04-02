"""
Miro Konzept Bot — Merlin generiert Konzepte, Bot platziert sie visuell auf Miro Boards.
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

# Row 1: Board + Concept Type
c1, c2 = st.columns([2, 1])

with c1:
    board_input = st.text_input(
        "Miro Board (URL oder ID)",
        placeholder="https://miro.com/app/board/uXjVK1234=/ oder Board-ID",
    )

with c2:
    CONCEPT_TYPE_OPTIONS = {
        "grobkonzept": "Grobkonzept — Überblick mit strategischen Eckpfeilern",
        "feinkonzept": "Feinkonzept — Detailliert mit konkreten Maßnahmen",
        "reels": "Reels-Konzept — Hooks, Szenen und CTAs",
    }
    concept_type = st.selectbox(
        "Konzept-Typ",
        options=list(CONCEPT_TYPE_OPTIONS.keys()),
        format_func=lambda k: CONCEPT_TYPE_OPTIONS[k],
    )

# Row 2: Customer Profile
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

# Row 3: Topic
thema = st.text_input(
    "Konzept-Thema / Briefing",
    placeholder="z.B. Social Media Strategie, Employer Branding Kampagne, Reel-Serie für Recruiting...",
)

# Row 4: File upload + Context
c3, c4 = st.columns(2)

with c3:
    uploaded_files = st.file_uploader(
        "Dateien (optional)",
        type=["pdf", "txt", "docx"],
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

if st.button("🚀 Konzept erstellen & auf Board platzieren", use_container_width=True,
             type="primary", disabled=(not board_input or not thema)):

    from miro_bot.miro_api import parse_board_id, MIRO_API_TOKEN
    from miro_bot.konzept_bot import generate_concept, place_concept_on_board

    if not MIRO_API_TOKEN:
        st.error("⚠️ `MIRO_API_TOKEN` nicht konfiguriert.")
        st.stop()

    board_id = parse_board_id(board_input)

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

    # Step 1: Generate concept via Merlin
    with st.spinner(f"🧠 Merlin erstellt {CONCEPT_TYPE_OPTIONS[concept_type].split(' —')[0]}..."):
        try:
            concept = generate_concept(
                thema=thema,
                concept_type=concept_type,
                profile=selected_profile,
                kontext=kontext,
                file_text=file_text.strip(),
            )
        except Exception as e:
            st.error(f"Konzept-Generierung fehlgeschlagen: {e}")
            st.stop()

    # Show preview
    st.markdown("### 📋 Konzept-Vorschau")
    st.markdown(f"**{concept.get('title', 'Konzept')}**")

    for section in concept.get("sections", []):
        with st.expander(section["heading"], expanded=True):
            for point in section.get("points", []):
                st.markdown(f"  {point}")

    st.markdown("---")

    # Step 2: Place on Miro board
    progress = st.progress(0, text="📐 Board wird vorbereitet...")

    try:
        result = place_concept_on_board(
            board_id, concept,
            progress_callback=lambda pct, text: progress.progress(min(pct, 1.0), text=text),
        )

        progress.empty()
        st.success(
            f"✅ {CONCEPT_TYPE_OPTIONS[concept_type].split(' —')[0]} **\"{result['title']}\"** erfolgreich platziert! "
            f"({result['items_created']} Elemente, {result['sections']} Abschnitte)"
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
