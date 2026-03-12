import streamlit as st
import json
import os
from streamlit.components.v1 import html as st_html
from shared import inject_css, load_profiles, render_color_swatches

st.set_page_config(page_title="Creative Generator", page_icon="🎨", layout="wide")
inject_css()

# ─── HEADER ──────────────────────────────────────────────────────────────────

st.markdown("# 🎨 Creative Generator")
st.markdown("KI-generierte Creatives basierend auf Trends, News und Competitor-Analyse.")
st.markdown("---")

# ─── INIT SESSION STATE ─────────────────────────────────────────────────────

if "creative_results_path" not in st.session_state:
    st.session_state["creative_results_path"] = None
if "creative_generating" not in st.session_state:
    st.session_state["creative_generating"] = False

# ─── PROFIL AUSWAHL ─────────────────────────────────────────────────────────

profiles = load_profiles()

if not profiles:
    st.error("Keine Kundenprofile vorhanden. Bitte zuerst ein Profil unter **Kundenprofile** anlegen.")
    st.stop()

profile_options = sorted(profiles.values(), key=lambda x: x["name"])
profile_names = [p["name"] for p in profile_options]
selected_profile_name = st.selectbox("👤 Kundenprofil auswählen", profile_names)

selected_profile = next((p for p in profile_options if p["name"] == selected_profile_name), None)
profile_slug = selected_profile["slug"] if selected_profile else None

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
    weeks = st.number_input("Wochen", min_value=1, max_value=52, value=4, step=1)
    posts_per_week = st.number_input("Posts pro Woche", min_value=1, max_value=7, value=2, step=1)

with col_right:
    notes = st.text_area(
        "Anmerkungen",
        placeholder="z.B. Fokus auf Recruiting, keine Produktwerbung, bestimmte Kampagne...",
        height=132,
    )

num_creatives = weeks * posts_per_week

st.markdown("<br>", unsafe_allow_html=True)

# ─── GENERATE BUTTON ────────────────────────────────────────────────────────

if st.button("🎨 Creatives generieren", use_container_width=True, type="primary"):
    st.session_state["creative_generating"] = True
    with st.spinner("Creatives werden generiert — Trends, News und Competitors werden analysiert..."):
        try:
            from creative_pipeline import run_creative_pipeline

            result_path = run_creative_pipeline(
                profile_slug=profile_slug,
                num_creatives=num_creatives,
                weeks=weeks,
                posts_per_week=posts_per_week,
                notes=notes,
            )
            st.session_state["creative_results_path"] = result_path
            st.session_state["creative_generating"] = False
            st.success(f"✅ {num_creatives} Creatives erfolgreich generiert!")
            st.rerun()
        except Exception as e:
            st.session_state["creative_generating"] = False
            st.error(f"Fehler bei der Generierung: {e}")

# ─── RESULTS SECTION ────────────────────────────────────────────────────────

results_path = f"outputs/creatives/latest_{profile_slug}.json"

# Try stored path first, then default path
active_path = st.session_state.get("creative_results_path") or results_path
creative_data = None

if active_path and os.path.exists(active_path):
    with open(active_path, "r", encoding="utf-8") as f:
        creative_data = json.load(f)
elif os.path.exists(results_path):
    with open(results_path, "r", encoding="utf-8") as f:
        creative_data = json.load(f)

if not creative_data:
    st.markdown("""
    <div style="text-align:center; padding: 80px 0;">
        <div style="font-size:64px;">🎨</div>
        <h2>Noch keine Creatives vorhanden</h2>
        <p style="color:#666;">Wähle ein Kundenprofil und klicke auf "Creatives generieren".</p>
    </div>
    """, unsafe_allow_html=True)
    st.stop()

# ─── STATS ───────────────────────────────────────────────────────────────────

st.markdown("---")

creatives = creative_data.get("creatives", [])
total_creatives = len(creatives)

# Type breakdown
type_counts = {}
for c in creatives:
    ctype = c.get("type", "unbekannt")
    type_counts[ctype] = type_counts.get(ctype, 0) + 1

# Source references count
all_sources = set()
for c in creatives:
    for ref in c.get("source_references", []):
        if isinstance(ref, str):
            all_sources.add(ref)
        elif isinstance(ref, dict):
            all_sources.add(ref.get("url", ref.get("title", "")))

stat_cols = st.columns(4)
stat_cols[0].metric("🎨 Creatives gesamt", total_creatives)
stat_cols[1].metric("📅 Wochen", creative_data.get("config", {}).get("weeks", "–"))
stat_cols[2].metric("📱 Typen", len(type_counts))
stat_cols[3].metric("🔗 Quellen", len(all_sources))

# Type breakdown chips
type_chips = ""
for t, count in type_counts.items():
    type_chips += f'<span class="stat-chip">{t}: {count}</span> '
st.markdown(type_chips, unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ─── CREATIVE GALLERY ───────────────────────────────────────────────────────

st.markdown(
    '<div class="week-header">🖼️ Creative Gallery</div>',
    unsafe_allow_html=True,
)

for idx, creative in enumerate(creatives, start=1):
    title = creative.get("title", "Untitled")
    ctype = creative.get("type", "–")

    with st.expander(f"**{idx}. {title}** — {ctype}", expanded=False):
        col_main, col_side = st.columns([2, 1])

        with col_main:
            png_path = creative.get("png_path", "")
            svg_path = creative.get("svg_path", "")

            # Show image preview
            if png_path and os.path.exists(png_path):
                st.image(png_path, use_container_width=True)
            elif svg_path and os.path.exists(svg_path) and svg_path.endswith(".svg") and "overlay" not in svg_path:
                with open(svg_path, "r", encoding="utf-8") as sf:
                    st.image(sf.read(), use_container_width=True)
            else:
                st.markdown(
                    '<div class="content-card" style="text-align:center;padding:60px 20px;">'
                    '<div style="font-size:36px;">🖼️</div>'
                    '<div style="color:#666;margin-top:8px;">Keine Vorschau verfügbar</div>'
                    '</div>',
                    unsafe_allow_html=True,
                )

            # Download buttons
            has_ai_image = png_path and os.path.exists(png_path) and png_path.endswith(".png")
            has_overlay = svg_path and os.path.exists(svg_path) and "overlay" in svg_path

            dl_col1, dl_col2 = st.columns(2)
            with dl_col1:
                if has_ai_image:
                    with open(png_path, "rb") as pf:
                        png_data = pf.read()
                    st.download_button(
                        label="⬇️ KI-Bild (PNG)",
                        data=png_data,
                        file_name=f"creative_{idx}_{profile_slug}.png",
                        mime="image/png",
                        use_container_width=True,
                        key=f"dl_png_{idx}",
                    )
                elif svg_path and os.path.exists(svg_path) and not has_overlay:
                    with open(svg_path, "r", encoding="utf-8") as sf:
                        svg_data = sf.read()
                    st.download_button(
                        label="⬇️ SVG (Fallback)",
                        data=svg_data,
                        file_name=f"creative_{idx}_{profile_slug}.svg",
                        mime="image/svg+xml",
                        use_container_width=True,
                        key=f"dl_svg_{idx}",
                    )
            with dl_col2:
                if has_overlay:
                    with open(svg_path, "r", encoding="utf-8") as sf:
                        svg_data = sf.read()
                    st.download_button(
                        label="⬇️ Text-Overlay (SVG für Canva)",
                        data=svg_data,
                        file_name=f"overlay_{idx}_{profile_slug}.svg",
                        mime="image/svg+xml",
                        use_container_width=True,
                        key=f"dl_overlay_{idx}",
                    )

            if has_overlay:
                st.markdown(
                    '<div style="font-size:11px;color:#666;margin-top:4px;">'
                    '💡 <b>Canva-Tipp:</b> PNG als Hintergrund importieren, '
                    'SVG-Overlay drüberlegen → Text & Logo sind editierbar!'
                    '</div>',
                    unsafe_allow_html=True,
                )

            # Caption
            caption = creative.get("caption", "")
            if caption:
                st.markdown('<div class="section-label">✍️ Caption</div>', unsafe_allow_html=True)
                st.markdown(f'<div class="caption-box">{caption}</div>', unsafe_allow_html=True)

            # Text Overlay
            text_overlay = creative.get("text_overlay", {})
            if text_overlay and text_overlay.get("enabled"):
                st.markdown('<div class="section-label" style="margin-top:12px;">📝 Text Overlay</div>',
                            unsafe_allow_html=True)
                overlay_text = text_overlay.get("text", "–")
                overlay_pos = text_overlay.get("position", "–")
                overlay_style = text_overlay.get("style", "–")
                st.markdown(
                    f'<div class="content-card" style="padding:14px;">'
                    f'<div style="font-size:14px;font-weight:700;">"{overlay_text}"</div>'
                    f'<div style="font-size:11px;color:#888;margin-top:6px;">'
                    f'Position: {overlay_pos} · Style: {overlay_style}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

        with col_side:
            # Mood
            mood = creative.get("mood", "")
            if mood:
                st.markdown('<div class="section-label">🎨 Mood</div>', unsafe_allow_html=True)
                st.markdown(f"*{mood}*")

            # Image Description
            img_desc = creative.get("image_description", "")
            if img_desc:
                st.markdown('<div class="section-label" style="margin-top:12px;">🖼️ Bildbeschreibung</div>',
                            unsafe_allow_html=True)
                st.markdown(f'<div style="font-size:13px;color:#aaa;">{img_desc}</div>',
                            unsafe_allow_html=True)

            # Colors
            colors = creative.get("colors", [])
            if colors:
                st.markdown('<div class="section-label" style="margin-top:12px;">🎨 Farbpalette</div>',
                            unsafe_allow_html=True)
                # Convert plain hex strings to dict format if needed
                color_dicts = []
                for c in colors:
                    if isinstance(c, dict):
                        color_dicts.append(c)
                    elif isinstance(c, str):
                        color_dicts.append({"name": "", "hex": c})
                st.markdown(render_color_swatches(color_dicts), unsafe_allow_html=True)

            # Reasoning
            reasoning = creative.get("reasoning", "")
            if reasoning:
                st.markdown('<div class="section-label" style="margin-top:12px;">💡 Reasoning</div>',
                            unsafe_allow_html=True)
                st.markdown(
                    f'<div style="font-size:13px;color:#aaa;background:#252525;'
                    f'border-radius:8px;padding:12px;">{reasoning}</div>',
                    unsafe_allow_html=True,
                )

            # Source References
            sources = creative.get("source_references", [])
            if sources:
                st.markdown('<div class="section-label" style="margin-top:12px;">🔗 Quellen</div>',
                            unsafe_allow_html=True)
                for src in sources:
                    if isinstance(src, str):
                        if src.startswith("http"):
                            st.markdown(
                                f'<a href="{src}" target="_blank" style="color:#4fa3e0;'
                                f'font-size:12px;word-break:break-all;">{src}</a><br>',
                                unsafe_allow_html=True,
                            )
                        else:
                            st.markdown(f'<div style="font-size:12px;color:#888;">📌 {src}</div>',
                                        unsafe_allow_html=True)
                    elif isinstance(src, dict):
                        url = src.get("url", "")
                        label = src.get("title", url)
                        if url:
                            st.markdown(
                                f'<a href="{url}" target="_blank" style="color:#4fa3e0;'
                                f'font-size:12px;word-break:break-all;">{label}</a><br>',
                                unsafe_allow_html=True,
                            )
                        else:
                            st.markdown(f'<div style="font-size:12px;color:#888;">📌 {label}</div>',
                                        unsafe_allow_html=True)

# ─── BULK DOWNLOAD ──────────────────────────────────────────────────────────

st.markdown("<br>", unsafe_allow_html=True)

st.download_button(
    label="⬇️ Alle Creatives als JSON herunterladen",
    data=json.dumps(creative_data, ensure_ascii=False, indent=2),
    file_name=f"creatives_{profile_slug}.json",
    mime="application/json",
    use_container_width=True,
)

st.markdown("<br><br>", unsafe_allow_html=True)
