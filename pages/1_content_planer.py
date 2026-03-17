import streamlit as st
import json
import os
from shared import (
    inject_css, load_latest_plan, load_all_plans, load_plan_by_filename,
    load_profiles, effort_badge, platform_badges, render_color_swatches,
    render_shot_list
)

st.set_page_config(page_title="Content Planer", page_icon="🎬", layout="wide")
inject_css()

# ─── HEADER ──────────────────────────────────────────────────────────────────

st.markdown("# 🎬 Content Planer")
st.markdown("KI-gestützte Content-Pläne mit visuellem Briefing, Shot Lists und TikTok-Referenzen.")
st.markdown("---")

# ─── INIT SESSION STATE ─────────────────────────────────────────────────────

if "plan_generating" not in st.session_state:
    st.session_state["plan_generating"] = False

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
    days = st.number_input("Tage", min_value=1, max_value=90, value=7, step=1)
    posts_per_day = st.number_input("Posts pro Tag", min_value=1, max_value=5, value=1, step=1)

with col_right:
    content_category = st.selectbox(
        "Content-Kategorie",
        ["Instagram Reel", "Ad (Werbevideo)", "Imagefilm", "Gemischt (alle Formate)"],
        index=0,
    )
    notes = st.text_area(
        "Anmerkungen",
        placeholder="z.B. Fokus auf Recruiting, bestimmte Kampagne, Themen vermeiden...",
        height=100,
    )

total_posts = days * posts_per_day

# ─── FILE UPLOAD ───────────────────────────────────────────────────────────
st.markdown('<div class="section-label">📎 Dateien einfügen (optional)</div>', unsafe_allow_html=True)
st.markdown("*PDFs (z.B. Stellenausschreibungen), Bilder oder Textdateien — werden in die Content-Konzeption einbezogen.*")
uploaded_files = st.file_uploader(
    "Dateien hochladen",
    type=["pdf", "png", "jpg", "jpeg", "webp", "txt", "docx"],
    accept_multiple_files=True,
    label_visibility="collapsed",
)
if uploaded_files:
    file_names = ", ".join(f.name for f in uploaded_files)
    st.info(f"📎 {len(uploaded_files)} Datei(en): {file_names}")

st.markdown("<br>", unsafe_allow_html=True)

# ─── GENERATE BUTTON ────────────────────────────────────────────────────────

if st.button("🎬 Content Plan generieren", use_container_width=True, type="primary"):
    st.session_state["plan_generating"] = True
    with st.spinner(f"Content Plan wird generiert — {total_posts} Posts für {days} Tage..."):
        try:
            from pipeline import run_pipeline_from_ui

            result_path = run_pipeline_from_ui(
                profile_slug=profile_slug,
                days=days,
                posts_per_day=posts_per_day,
                notes=notes,
                content_category=content_category,
                uploaded_files=uploaded_files if uploaded_files else [],
            )
            st.session_state["plan_generating"] = False
            st.session_state["selected_plan_file"] = os.path.basename(result_path)
            st.success(f"✅ {total_posts} Posts erfolgreich generiert!")
            st.rerun()
        except Exception as e:
            st.session_state["plan_generating"] = False
            st.error(f"Fehler bei der Generierung: {e}")

st.markdown("---")

# ─── PLAN AUSWAHL ───────────────────────────────────────────────────────────

all_plans = load_all_plans()

# Filter plans for current profile if desired
if all_plans:
    st.markdown('<div class="section-label">📁 Gespeicherte Content Pläne</div>', unsafe_allow_html=True)

    # Build display labels
    plan_labels = ["📌 Aktuellster Plan (latest)"]
    for f in all_plans:
        # Try to extract metadata for label
        label = f.replace(".json", "").replace("_", " ")
        plan_labels.append(f"📄 {label}")

    selected_plan_idx = 0
    # If we just generated a plan, pre-select it
    if "selected_plan_file" in st.session_state:
        target = st.session_state["selected_plan_file"]
        if target in all_plans:
            selected_plan_idx = all_plans.index(target) + 1  # +1 because of "latest" at index 0

    selected_plan_label = st.selectbox(
        "Plan auswählen",
        plan_labels,
        index=selected_plan_idx,
        key="plan_selector",
    )

    # Load selected plan
    if selected_plan_label == plan_labels[0]:
        plan_data = load_latest_plan()
    else:
        plan_idx = plan_labels.index(selected_plan_label) - 1
        plan_data = load_plan_by_filename(all_plans[plan_idx])
else:
    plan_data = load_latest_plan()

# ─── NO PLAN STATE ──────────────────────────────────────────────────────────

if not plan_data:
    st.markdown("""
    <div style="text-align:center; padding: 80px 0;">
        <div style="font-size:64px;">🎬</div>
        <h2>Noch kein Content Plan vorhanden</h2>
        <p style="color:#666;">Wähle ein Kundenprofil und klicke auf "Content Plan generieren".</p>
    </div>
    """, unsafe_allow_html=True)
    st.stop()

plan = plan_data.get("plan", [])

# ─── PLAN INFO + FILTERS ────────────────────────────────────────────────────

st.markdown("<br>", unsafe_allow_html=True)

info_col1, info_col2, info_col3 = st.columns(3)
info_col1.markdown(f"**Kunde:** {plan_data.get('client', '–')}")
info_col2.markdown(f"**Erstellt:** {plan_data.get('generated_at', '–')}")
info_col3.markdown(f"**Profil:** {plan_data.get('profile', '–')}")

st.markdown("<br>", unsafe_allow_html=True)

# Filters
filter_col1, filter_col2 = st.columns(2)
with filter_col1:
    platform_filter = st.multiselect(
        "Plattform filtern",
        ["TikTok", "Instagram Reel", "Instagram Post", "YouTube", "LinkedIn"],
        default=[]
    )
with filter_col2:
    effort_filter = st.multiselect(
        "Aufwand filtern",
        ["Niedrig", "Mittel", "Hoch"],
        default=[]
    )

# Apply filters
if platform_filter:
    plan = [e for e in plan if any(
        p in (e.get("platform") if isinstance(e.get("platform"), list) else [e.get("platform", "")])
        for p in platform_filter
    )]

if effort_filter:
    plan = [e for e in plan if
        e.get("visual_briefing", {}).get("effort", "").capitalize() in effort_filter
    ]

# ─── STATS ROW ───────────────────────────────────────────────────────────────

st.markdown("---")

total = len(plan_data.get("plan", []))
platforms_used = set()
for e in plan_data.get("plan", []):
    p = e.get("platform", [])
    if isinstance(p, list):
        platforms_used.update(p)
    else:
        platforms_used.add(p)

col1, col2, col3, col4 = st.columns(4)
col1.metric("📅 Posts gesamt", total)
col2.metric("📱 Plattformen", len(platforms_used))
col3.metric("📆 Wochen", max(1, total // 7))
col4.metric("⚡ Gefiltert", len(plan))

st.markdown("<br>", unsafe_allow_html=True)

# ─── JSON EXPORT ─────────────────────────────────────────────────────────────

st.download_button(
    label="⬇️ JSON Export",
    data=json.dumps(plan_data, ensure_ascii=False, indent=2),
    file_name=f"contentplan_{plan_data.get('client', 'export')}.json",
    mime="application/json",
    use_container_width=True
)

st.markdown("<br>", unsafe_allow_html=True)

# ─── CONTENT CARDS ───────────────────────────────────────────────────────────

weeks = {}
for entry in plan:
    week = entry.get("week", 1)
    weeks.setdefault(week, []).append(entry)

for week_num, entries in weeks.items():
    week_theme = entries[0].get("week_theme", f"Woche {week_num}")
    st.markdown(
        f'<div class="week-header">📅 Woche {week_num}: {week_theme}</div>',
        unsafe_allow_html=True
    )

    for entry in entries:
        vb = entry.get("visual_briefing", {})
        day = entry.get("day", "")
        topic = entry.get("topic", "")
        hook = entry.get("hook", "")
        caption = entry.get("caption", "")
        best_time = entry.get("best_time", "")
        platform = entry.get("platform", [])
        fmt = entry.get("format", "")

        with st.expander(f"**{day}** — {topic}", expanded=False):
            col_left, col_right = st.columns([2, 1])

            with col_left:
                st.markdown(
                    platform_badges(platform) +
                    f'<span class="format-badge">🎥 {fmt}</span>',
                    unsafe_allow_html=True
                )
                st.markdown("<br>", unsafe_allow_html=True)

                st.markdown('<div class="section-label">🎣 Hook</div>', unsafe_allow_html=True)
                st.markdown(
                    f'<div class="hook-box">"{hook}"</div>',
                    unsafe_allow_html=True
                )

                st.markdown('<div class="section-label" style="margin-top:16px;">✍️ Caption</div>',
                            unsafe_allow_html=True)
                st.markdown(
                    f'<div class="caption-box">{caption}</div>',
                    unsafe_allow_html=True
                )

                st.markdown("<br>", unsafe_allow_html=True)
                st.markdown(
                    f'<span class="time-badge">🕐 Best Time: {best_time}</span>',
                    unsafe_allow_html=True
                )

            with col_right:
                if vb:
                    st.markdown('<div class="section-label">🎨 Mood</div>', unsafe_allow_html=True)
                    st.markdown(f"*{vb.get('mood', '–')}*")

                    st.markdown('<div class="section-label" style="margin-top:12px;">🎨 Farbpalette</div>',
                                unsafe_allow_html=True)
                    st.markdown(
                        render_color_swatches(vb.get("colors", [])),
                        unsafe_allow_html=True
                    )

                    st.markdown('<div class="section-label" style="margin-top:12px;">👁️ Referenz</div>',
                                unsafe_allow_html=True)
                    st.markdown(f"📌 {vb.get('reference_creator', '–')}")

                    st.markdown('<div class="section-label" style="margin-top:12px;">⚙️ Produktion</div>',
                                unsafe_allow_html=True)
                    st.markdown(
                        effort_badge(vb.get("effort", "")),
                        unsafe_allow_html=True
                    )
                    st.markdown(f"🎙️ {vb.get('equipment', '–')}")
                    st.markdown(f"⏱️ ~{vb.get('duration_seconds', '?')} Sek.")

            if vb.get("shots"):
                st.markdown("---")
                st.markdown('<div class="section-label">🎬 Shot List</div>', unsafe_allow_html=True)
                st.markdown(render_shot_list(vb.get("shots", [])), unsafe_allow_html=True)

            if vb.get("pacing") or vb.get("music_mood"):
                col_a, col_b, col_c = st.columns(3)
                with col_a:
                    st.markdown('<div class="section-label">⚡ Pacing</div>', unsafe_allow_html=True)
                    st.markdown(f"✂️ {vb.get('pacing', '–')} · {vb.get('transition', '–')}")
                with col_b:
                    st.markdown('<div class="section-label">🎵 Musik</div>', unsafe_allow_html=True)
                    st.markdown(f"{vb.get('music_mood', '–')} – {vb.get('music_example', '–')}")
                with col_c:
                    st.markdown('<div class="section-label">🖼️ Thumbnail</div>', unsafe_allow_html=True)
                    st.markdown(f"{vb.get('thumbnail_frame', '–')}")

            if vb.get("production_notes"):
                st.markdown("---")
                st.info(f"📋 **Notizen:** {vb.get('production_notes')}")

            refs = entry.get("reference_videos", [])
            if refs:
                st.markdown("---")
                st.markdown('<div class="section-label">🔗 Referenzvideos</div>', unsafe_allow_html=True)
                ref_cols = st.columns(min(len(refs), 3))
                for ridx, ref in enumerate(refs[:3]):
                    with ref_cols[ridx]:
                        views = ref.get("views", 0)
                        if views >= 1_000_000:
                            views_str = f"{views/1_000_000:.1f}M"
                        elif views >= 1_000:
                            views_str = f"{views/1_000:.0f}K"
                        else:
                            views_str = str(views)
                        st.markdown(f"""
                        <div class="content-card" style="padding:14px;">
                            <div style="font-size:11px;color:#e63946;font-weight:700;">{ref.get('platform','TikTok')} · @{ref.get('author','?')}</div>
                            <div style="font-size:12px;color:#aaa;margin:6px 0;">{ref.get('description','')[:80]}...</div>
                            <div style="font-size:11px;color:#666;">👁 {views_str} · ❤️ {ref.get('likes',0):,}</div>
                            <a href="{ref.get('url','#')}" target="_blank" style="display:inline-block;margin-top:8px;background:#e63946;color:white;padding:4px 12px;border-radius:6px;font-size:11px;text-decoration:none;">Video ansehen →</a>
                        </div>
                        """, unsafe_allow_html=True)

st.markdown("<br><br>", unsafe_allow_html=True)
