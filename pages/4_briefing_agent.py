import streamlit as st
import json
from shared import inject_css, load_profiles, platform_badges, render_color_swatches
from briefing_agent import run_briefing_agent, load_all_briefing_files, load_briefing_file

st.set_page_config(page_title="Briefing Agent", page_icon="📋", layout="wide")
inject_css()

# ─── HEADER ──────────────────────────────────────────────────────────────────

st.markdown("# 📋 Briefing Agent")
st.markdown("KI-gestützter Trend-Research und automatische Content-Briefings mit Claude AI.")
st.markdown("---")

# ─── INIT SESSION STATE ─────────────────────────────────────────────────────

if "briefing_generating" not in st.session_state:
    st.session_state["briefing_generating"] = False
if "briefing_log" not in st.session_state:
    st.session_state["briefing_log"] = []
if "briefing_results" not in st.session_state:
    st.session_state["briefing_results"] = None

# ─── PROFIL AUSWAHL ─────────────────────────────────────────────────────────

profiles = load_profiles()

if not profiles:
    st.error("Keine Kundenprofile vorhanden. Bitte zuerst ein Profil unter **Kundenprofile** anlegen.")
    st.stop()

profile_options = sorted(profiles.values(), key=lambda x: x["name"])
profile_names = [p["name"] for p in profile_options]
selected_profile_name = st.selectbox("👤 Kundenprofil auswählen", profile_names)

selected_profile = next((p for p in profile_options if p["name"] == selected_profile_name), None)

# CI Preview
if selected_profile:
    ci_colors = ""
    for c in selected_profile.get("colors", []):
        ci_colors += (
            f'<div style="display:inline-block;width:18px;height:18px;'
            f'background:{c["hex"]};border-radius:4px;border:1px solid #333;'
            f'margin-right:3px;vertical-align:middle;"></div>'
        )
    st.markdown(
        f'{ci_colors} '
        f'<span style="color:#888;font-size:13px;vertical-align:middle;">'
        f'{selected_profile.get("industry", "")} · {selected_profile["name"]}</span>',
        unsafe_allow_html=True,
    )

st.markdown("<br>", unsafe_allow_html=True)

# ─── KONFIGURATION ──────────────────────────────────────────────────────────

st.markdown('<div class="section-label">⚙️ Konfiguration</div>', unsafe_allow_html=True)

col_left, col_right = st.columns(2)

with col_left:
    num_briefings = st.number_input("Anzahl Briefings", min_value=1, max_value=20, value=5, step=1)
    platform_options = ["TikTok", "Instagram Reel", "Instagram Post", "YouTube", "LinkedIn"]
    selected_platforms = st.multiselect("Zielplattformen", platform_options, default=["TikTok", "Instagram Reel"])

with col_right:
    focus = st.text_area(
        "Fokus / Thema",
        placeholder="z.B. Recruiting-Kampagne, Sommersale, Behind the Scenes...",
        height=132,
    )

st.markdown("<br>", unsafe_allow_html=True)

# ─── GENERATE BUTTON ────────────────────────────────────────────────────────

if st.button("📋 Briefings generieren", use_container_width=True, type="primary"):
    if not selected_profile:
        st.error("Bitte ein Kundenprofil auswählen.")
    else:
        st.session_state["briefing_generating"] = True
        st.session_state["briefing_log"] = []
        st.session_state["briefing_results"] = None

        log_container = st.empty()
        status_logs = []

        def on_status(msg):
            status_logs.append(msg)
            log_container.markdown(
                "\n".join([f"- {m}" for m in status_logs]),
            )

        with st.spinner(f"Briefing Agent arbeitet – {num_briefings} Briefings für {selected_profile['name']}..."):
            try:
                results = run_briefing_agent(
                    profile=selected_profile,
                    num_briefings=num_briefings,
                    focus=focus,
                    platforms=selected_platforms,
                    on_status=on_status,
                )
                st.session_state["briefing_generating"] = False
                st.session_state["briefing_results"] = results
                st.success(f"✅ {len(results)} Briefings erfolgreich generiert!")
                st.rerun()
            except Exception as e:
                st.session_state["briefing_generating"] = False
                st.error(f"Fehler: {e}")

st.markdown("---")

# ─── SAVED BRIEFINGS SELECTOR ───────────────────────────────────────────────

all_files = load_all_briefing_files()

if all_files or st.session_state.get("briefing_results"):
    st.markdown('<div class="section-label">📁 Gespeicherte Briefings</div>', unsafe_allow_html=True)

    if all_files:
        file_labels = [f.replace(".json", "").replace("_", " ") for f in all_files]
        selected_file_label = st.selectbox("Briefing-Set auswählen", file_labels, key="briefing_file_selector")
        selected_file_idx = file_labels.index(selected_file_label)
        briefing_data = load_briefing_file(all_files[selected_file_idx])
    else:
        briefing_data = None

    # Use just-generated results if available and no file selected
    if st.session_state.get("briefing_results") and not briefing_data:
        briefings = st.session_state["briefing_results"]
        client_name = selected_profile["name"] if selected_profile else "?"
        generated_at = ""
    elif briefing_data:
        briefings = briefing_data.get("briefings", [])
        client_name = briefing_data.get("client", "?")
        generated_at = briefing_data.get("generated_at", "")
    else:
        briefings = []
        client_name = ""
        generated_at = ""

    if briefings:
        # ─── INFO ROW ───────────────────────────────────────────────────────
        info_c1, info_c2, info_c3 = st.columns(3)
        info_c1.markdown(f"**Kunde:** {client_name}")
        info_c2.markdown(f"**Erstellt:** {generated_at}")
        info_c3.markdown(f"**Briefings:** {len(briefings)}")

        st.markdown("<br>", unsafe_allow_html=True)

        # ─── JSON EXPORT ────────────────────────────────────────────────────
        export_data = briefing_data if briefing_data else {
            "client": client_name,
            "briefings": briefings,
        }
        st.download_button(
            label="⬇️ JSON Export",
            data=json.dumps(export_data, ensure_ascii=False, indent=2),
            file_name=f"briefings_{client_name.lower().replace(' ', '_')}.json",
            mime="application/json",
            use_container_width=True,
        )

        st.markdown("<br>", unsafe_allow_html=True)

        # ─── BRIEFING CARDS ─────────────────────────────────────────────────

        for idx, b in enumerate(briefings):
            relevanz = b.get("relevanz_score", "?")
            if isinstance(relevanz, (int, float)):
                if relevanz >= 8:
                    score_color = "#2ecc71"
                    score_label = "🔥 Hoch"
                elif relevanz >= 5:
                    score_color = "#f39c12"
                    score_label = "📈 Mittel"
                else:
                    score_color = "#e74c3c"
                    score_label = "📉 Niedrig"
            else:
                score_color = "#888"
                score_label = "?"

            titel = b.get("titel", f"Briefing {idx+1}")
            with st.expander(f"**#{idx+1}** — {titel}  ·  Relevanz: {relevanz}/10", expanded=False):
                col_l, col_r = st.columns([2, 1])

                with col_l:
                    # Trend source & format
                    st.markdown(
                        f'<span class="platform-badge">{b.get("format", "?")}</span>'
                        f'<span class="format-badge">📊 {b.get("trend_quelle", "?")}</span>'
                        f'<span style="color:{score_color};font-weight:700;font-size:13px;margin-left:8px;">{score_label}</span>',
                        unsafe_allow_html=True,
                    )
                    st.markdown("<br>", unsafe_allow_html=True)

                    # Hook
                    st.markdown('<div class="section-label">🎣 Hook</div>', unsafe_allow_html=True)
                    hook = b.get("hook", "–")
                    st.markdown(f'<div class="hook-box">"{hook}"</div>', unsafe_allow_html=True)

                    # Caption
                    st.markdown('<div class="section-label" style="margin-top:16px;">✍️ Caption</div>', unsafe_allow_html=True)
                    st.markdown(
                        f'<div class="caption-box">{b.get("caption_idee", "–")}</div>',
                        unsafe_allow_html=True,
                    )

                    # Hashtags
                    hashtags = b.get("hashtags", [])
                    if hashtags:
                        st.markdown('<div class="section-label" style="margin-top:16px;">🏷️ Hashtags</div>', unsafe_allow_html=True)
                        tags_html = " ".join([f'<span class="format-badge">#{h.lstrip("#")}</span>' for h in hashtags])
                        st.markdown(tags_html, unsafe_allow_html=True)

                    st.markdown("<br>", unsafe_allow_html=True)
                    st.markdown(
                        f'<span class="time-badge">🕐 Best Time: {b.get("best_post_time", "–")}</span>',
                        unsafe_allow_html=True,
                    )

                with col_r:
                    # Target audience
                    st.markdown('<div class="section-label">🎯 Zielgruppe</div>', unsafe_allow_html=True)
                    st.markdown(f"*{b.get('zielgruppe', '–')}*")

                    # Tonality
                    st.markdown('<div class="section-label" style="margin-top:12px;">🗣️ Ton</div>', unsafe_allow_html=True)
                    st.markdown(f"{b.get('ton', '–')}")

                    # Colors
                    colors = b.get("farben", [])
                    if colors:
                        st.markdown('<div class="section-label" style="margin-top:12px;">🎨 Farbpalette</div>', unsafe_allow_html=True)
                        if isinstance(colors, list) and colors and isinstance(colors[0], dict):
                            st.markdown(render_color_swatches(colors), unsafe_allow_html=True)
                        elif isinstance(colors, list):
                            color_html = ""
                            for c in colors:
                                hex_val = c if isinstance(c, str) else str(c)
                                color_html += f'<div style="display:inline-block;width:30px;height:30px;background:{hex_val};border-radius:6px;border:2px solid #333;margin-right:6px;"></div>'
                            st.markdown(color_html, unsafe_allow_html=True)

                    # What to avoid
                    vermeiden = b.get("was_vermeiden", "")
                    if vermeiden:
                        st.markdown('<div class="section-label" style="margin-top:12px;">⚠️ Vermeiden</div>', unsafe_allow_html=True)
                        st.markdown(f"❌ {vermeiden}")

                # Slide structure
                slides = b.get("slide_struktur", [])
                if slides:
                    st.markdown("---")
                    st.markdown('<div class="section-label">🎬 Slide / Shot Struktur</div>', unsafe_allow_html=True)
                    for si, slide in enumerate(slides):
                        if isinstance(slide, dict):
                            desc = slide.get("beschreibung", slide.get("description", str(slide)))
                            st.markdown(f'<div class="shot-item">🎬 <b>Slide {si+1}:</b> {desc}</div>', unsafe_allow_html=True)
                        elif isinstance(slide, str):
                            st.markdown(f'<div class="shot-item">🎬 <b>Slide {si+1}:</b> {slide}</div>', unsafe_allow_html=True)

else:
    st.markdown("""
    <div style="text-align:center; padding: 80px 0;">
        <div style="font-size:64px;">📋</div>
        <h2>Noch keine Briefings vorhanden</h2>
        <p style="color:#666;">Wähle ein Kundenprofil und klicke auf "Briefings generieren".</p>
    </div>
    """, unsafe_allow_html=True)

st.markdown("<br><br>", unsafe_allow_html=True)
