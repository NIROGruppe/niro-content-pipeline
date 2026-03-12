import streamlit as st
from shared import inject_css

st.set_page_config(
    page_title="NIRO Tools",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded"
)

inject_css()

# ─── LANDING PAGE ────────────────────────────────────────────────────────────

st.markdown("""
<div style="text-align:center; padding: 40px 0 20px 0;">
    <div style="font-size:48px; font-weight:800; letter-spacing:-1px;">🚀 NIRO Tools</div>
    <p style="color:#888; font-size:16px; margin-top:8px;">Wähle ein Tool aus der Sidebar oder klicke unten.</p>
</div>
""", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

col1, col2 = st.columns(2)

with col1:
    st.markdown("""
    <div class="app-card">
        <div class="icon">🎬</div>
        <div class="title">Content Planer</div>
        <div class="desc">KI-gestützte Content-Pläne mit visuellem Briefing, Shot Lists und TikTok-Referenzen.</div>
    </div>
    """, unsafe_allow_html=True)
    if st.button("Content Planer öffnen", use_container_width=True):
        st.switch_page("pages/1_content_planer.py")

with col2:
    st.markdown("""
    <div class="app-card">
        <div class="icon">👤</div>
        <div class="title">Kundenprofile</div>
        <div class="desc">Corporate Identities anlegen – manuell oder automatisch aus CI-PDFs.</div>
    </div>
    """, unsafe_allow_html=True)
    if st.button("Kundenprofile öffnen", use_container_width=True):
        st.switch_page("pages/2_kundenprofile.py")

col3, col4 = st.columns(2)

with col3:
    st.markdown("""
    <div class="app-card">
        <div class="icon">🎨</div>
        <div class="title">Creative Generator</div>
        <div class="desc">KI-generierte Creatives basierend auf Trends, News und Competitor-Analyse.</div>
    </div>
    """, unsafe_allow_html=True)
    if st.button("Creative Generator öffnen", use_container_width=True):
        st.switch_page("pages/3_creative_generator.py")

with col4:
    st.markdown("""
    <div class="app-card">
        <div class="icon">📋</div>
        <div class="title">Briefing Agent</div>
        <div class="desc">KI-gestützter Trend-Research und automatische Content-Briefings mit Claude AI.</div>
    </div>
    """, unsafe_allow_html=True)
    if st.button("Briefing Agent öffnen", use_container_width=True):
        st.switch_page("pages/4_briefing_agent.py")

st.markdown("<br><br>", unsafe_allow_html=True)
st.markdown("<div style='text-align:center;color:#333;font-size:11px;'>NIRO Media GmbH © 2026</div>",
            unsafe_allow_html=True)
