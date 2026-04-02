"""
Miro Konzept Bot — Merlin generiert Konzepte, Bot platziert sie visuell auf Miro Boards.
"""
import streamlit as st
from shared import inject_css

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
    "Miro Board (URL oder ID)",
    placeholder="https://miro.com/app/board/uXjVK1234=/ oder Board-ID",
)

thema = st.text_input(
    "Konzept-Thema",
    placeholder="z.B. Social Media Strategie für Hochzeitsplaner",
)

kontext = st.text_area(
    "Zusätzlicher Kontext (optional)",
    placeholder="z.B. Kundenname, Branche, besondere Anforderungen...",
    height=100,
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

    # Step 1: Generate concept via Merlin
    with st.spinner("🧠 Merlin erstellt Konzept..."):
        try:
            concept = generate_concept(thema, kontext)
        except Exception as e:
            st.error(f"Konzept-Generierung fehlgeschlagen: {e}")
            st.stop()

    # Show preview
    st.markdown("### 📋 Konzept-Vorschau")
    st.markdown(f"**{concept.get('title', 'Konzept')}**")

    for section in concept.get("sections", []):
        with st.expander(section["heading"], expanded=True):
            for point in section.get("points", []):
                st.markdown(f"- {point}")

    st.markdown("---")

    # Step 2: Place on Miro board
    progress = st.progress(0, text="📐 Board wird vorbereitet...")

    try:
        result = place_concept_on_board(
            board_id, concept,
            progress_callback=lambda pct, text: progress.progress(pct, text=text),
        )

        progress.empty()
        st.success(
            f"✅ Konzept **\"{result['title']}\"** erfolgreich platziert! "
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
