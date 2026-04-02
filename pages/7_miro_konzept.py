"""
Miro Konzept Bot — Research → Ideen-Vorschau → Approval → Konzept aufs Board.
"""
import streamlit as st
from shared import inject_css, load_profiles, extract_text_from_pdf

st.set_page_config(page_title="Miro Konzept Bot", page_icon="🎨", layout="wide")
inject_css()

st.markdown("""
<div style="text-align:center; padding: 20px 0;">
    <div style="font-size:36px; font-weight:800;">🎨 Miro Konzept Bot</div>
    <p style="color:#888; font-size:14px;">Research → Ideen → Approval → Konzept aufs Miro Board</p>
</div>
""", unsafe_allow_html=True)

st.markdown("---")

# ─── STEP 1: CONFIG ───────────────────────────────────────────────────────

st.markdown('<div class="section-label">⚙️ Konfiguration</div>', unsafe_allow_html=True)

# Board + Template
c1, c2 = st.columns([2, 1])
with c1:
    board_input = st.text_input(
        "Ziel Miro Board (URL oder ID)",
        placeholder="https://miro.com/app/board/uXjVK1234=/",
    )
with c2:
    if "miro_templates" not in st.session_state:
        st.session_state["miro_templates"] = None
    if st.button("🔄 Templates laden"):
        with st.spinner("Templates laden..."):
            try:
                from miro_bot.template_bot import read_templates
                st.session_state["miro_templates"] = read_templates()
                st.rerun()
            except Exception as e:
                st.error(f"Fehler: {e}")

templates = st.session_state.get("miro_templates")
selected_template = None
if templates:
    selected_template = st.selectbox("Template", options=list(templates.keys()))
else:
    st.info("Klicke 'Templates laden' für Vorlagen.")

# Customer Profile
profiles = load_profiles()
profile_options = {"(Kein Profil)": None}
profile_options.update({p.get("name", slug): p for slug, p in profiles.items()})
selected_profile_name = st.selectbox("Kundenprofil", options=list(profile_options.keys()))
selected_profile = profile_options[selected_profile_name]

# Videos
st.markdown('<div class="section-label">🎬 Videos</div>', unsafe_allow_html=True)

num_videos = st.slider("Anzahl Videos", min_value=1, max_value=10, value=1)
video_themen = []
for v in range(num_videos):
    video_themen.append(st.text_input(
        f"Video {v + 1} — Thema",
        placeholder="z.B. Employer Branding, Behind the Scenes, Recruiting Reel...",
        key=f"video_thema_{v}",
    ))

# Files + Context
c3, c4 = st.columns(2)
with c3:
    uploaded_files = st.file_uploader(
        "Dateien (optional)",
        type=["pdf", "txt"],
        accept_multiple_files=True,
        help="z.B. Stellenanzeigen, Briefings",
    )
with c4:
    kontext = st.text_area(
        "Zusätzlicher Kontext (optional)",
        placeholder="Besondere Anforderungen, Ziele...",
        height=130,
    )

st.markdown("---")

# ─── STEP 2: RESEARCH + IDEAS ────────────────────────────────────────────

has_themen = any(t.strip() for t in video_themen)
industry = selected_profile.get("industry", "") if selected_profile else ""

if st.button("🔍 Research starten & Ideen generieren", use_container_width=True,
             disabled=not has_themen):

    # Extract file text
    file_text = ""
    if uploaded_files:
        for uf in uploaded_files:
            if uf.name.endswith(".pdf"):
                try:
                    file_text += extract_text_from_pdf(uf) + "\n\n"
                except Exception:
                    pass
            elif uf.name.endswith(".txt"):
                file_text += uf.read().decode("utf-8", errors="ignore") + "\n\n"

    from miro_bot.research import run_research, generate_video_ideas

    # Research
    active_themen = [t for t in video_themen if t.strip()]
    search_industry = industry or active_themen[0]

    progress = st.progress(0, text="🔍 Research läuft...")
    try:
        research = run_research(
            industry=search_industry,
            video_themen=active_themen,
            profile=selected_profile,
            progress_callback=lambda p, t: progress.progress(min(p, 1.0), text=t),
        )
        progress.empty()
    except Exception as e:
        progress.empty()
        st.error(f"Research fehlgeschlagen: {e}")
        st.stop()

    st.session_state["research"] = research
    st.session_state["file_text"] = file_text

    # Show research results
    st.markdown("### 🔍 Research Ergebnisse")

    r_col1, r_col2, r_col3 = st.columns(3)
    with r_col1:
        st.markdown(f"**TikTok Trends** ({len(research['tiktok'])})")
        for t in research["tiktok"][:5]:
            st.markdown(
                f'<div style="background:#1e1e1e;border-radius:8px;padding:10px;margin-bottom:6px;font-size:12px;">'
                f'<b>{t["author"]}</b> · {t["views"]:,} Views<br>'
                f'{t["description"][:80]}...<br>'
                f'<a href="{t["url"]}" target="_blank" style="color:#4fa3e0;">Link</a>'
                f'</div>', unsafe_allow_html=True
            )

    with r_col2:
        st.markdown(f"**Meta Ads Library** ({len(research['meta_ads'])})")
        for m in research["meta_ads"][:5]:
            platforms = ", ".join(m.get("platforms", [])) if m.get("platforms") else ""
            st.markdown(
                f'<div style="background:#1e1e1e;border-radius:8px;padding:10px;margin-bottom:6px;font-size:12px;">'
                f'<b>{m.get("page_name", "?")}</b>'
                f'{f" · {platforms}" if platforms else ""}'
                f'{f" · {m.get(\"format\", \"\")}" if m.get("format") else ""}<br>'
                f'{m.get("ad_text", "")[:100]}...<br>'
                f'{f"CTA: {m[\"cta\"]}" if m.get("cta") else ""}'
                f'</div>', unsafe_allow_html=True
            )

    with r_col3:
        st.markdown(f"**Branchennews** ({len(research['news'])})")
        for n in research["news"][:5]:
            st.markdown(
                f'<div style="background:#1e1e1e;border-radius:8px;padding:10px;margin-bottom:6px;font-size:12px;">'
                f'<b>{n["title"][:60]}</b><br>'
                f'{n["snippet"][:80]}...<br>'
                f'<a href="{n["url"]}" target="_blank" style="color:#4fa3e0;">Link</a>'
                f'</div>', unsafe_allow_html=True
            )

    st.markdown("---")

    # Generate ideas
    with st.spinner("🧠 Merlin entwickelt Video-Ideen..."):
        try:
            ideas = generate_video_ideas(
                research=research,
                video_themen=active_themen,
                profile=selected_profile,
                kontext=kontext,
                file_text=file_text.strip(),
            )
        except Exception as e:
            st.error(f"Ideen-Generierung fehlgeschlagen: {e}")
            st.stop()

    st.session_state["video_ideas"] = ideas

    st.markdown("### 💡 Video-Ideen")
    for idea in ideas:
        vnum = idea.get("video_num", "?")
        st.markdown(
            f'<div style="background:#1e1e1e;border:1px solid #2a2a2a;border-radius:12px;'
            f'padding:20px;margin-bottom:12px;">'
            f'<div style="font-size:11px;color:#888;">Video {vnum} · {idea.get("thema", "")}</div>'
            f'<div style="font-size:18px;font-weight:700;margin:6px 0;">{idea.get("idea_title", "")}</div>'
            f'<div style="font-size:14px;color:#ccc;margin-bottom:8px;">{idea.get("idea_summary", "")}</div>'
            f'<div style="font-size:12px;color:#888;">Inspiration: {idea.get("inspiration", "")}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    st.success(f"✅ {len(ideas)} Video-Ideen generiert. Prüfe die Ideen und klicke unten auf 'Konzepte erstellen'.")

st.markdown("---")

# ─── STEP 3: APPROVE + GENERATE CONCEPTS ─────────────────────────────────

ideas = st.session_state.get("video_ideas", [])
research = st.session_state.get("research", {})

if ideas and templates and selected_template and board_input:
    st.markdown('<div class="section-label">✅ Konzepte erstellen</div>', unsafe_allow_html=True)
    st.caption(f"{len(ideas)} Video-Ideen bereit · Template: {selected_template}")

    if st.button("🚀 Ideen approved — Konzepte erstellen & auf Board platzieren",
                 use_container_width=True, type="primary"):

        from miro_bot.miro_api import parse_board_id, MIRO_API_TOKEN
        from miro_bot.template_bot import generate_content_for_fields, place_template_on_board

        if not MIRO_API_TOKEN:
            st.error("⚠️ `MIRO_API_TOKEN` nicht konfiguriert.")
            st.stop()

        board_id = parse_board_id(board_input)
        tpl = templates[selected_template]
        fields = tpl.get("fields", [])
        file_text = st.session_state.get("file_text", "")

        total_created = 0
        total_fields = 0

        for idea in ideas:
            vnum = idea.get("video_num", "?")
            thema = idea.get("thema", "")
            idea_context = (
                f"Arbeitstitel: {idea.get('idea_title', '')}\n"
                f"Kernidee: {idea.get('idea_summary', '')}\n"
                f"Inspiration: {idea.get('inspiration', '')}"
            )

            st.markdown(f"### 🎬 Video {vnum}: {idea.get('idea_title', thema)}")

            with st.spinner(f"🧠 Merlin erstellt Konzept für Video {vnum}..."):
                try:
                    full_kontext = f"{kontext}\n\n{idea_context}" if kontext else idea_context
                    generated = generate_content_for_fields(
                        fields=fields,
                        thema=thema,
                        template_name=selected_template,
                        profile=selected_profile,
                        kontext=full_kontext,
                        file_text=file_text.strip(),
                    )
                except Exception as e:
                    st.error(f"Video {vnum} fehlgeschlagen: {e}")
                    continue

            for label, content in generated.items():
                with st.expander(f"{label}", expanded=False):
                    st.write(content)

            progress = st.progress(0, text=f"📐 Video {vnum} auf Board platzieren...")
            try:
                result = place_template_on_board(
                    target_board_id=board_id,
                    template_name=selected_template,
                    generated_content=generated,
                    templates=templates,
                    progress_callback=lambda pct, text: progress.progress(min(pct, 1.0), text=text),
                )
                progress.empty()
                total_created += result["items_created"]
                total_fields += result["fields_filled"]
                st.success(f"✅ Video {vnum} platziert")
            except Exception as e:
                progress.empty()
                st.error(f"Video {vnum} Platzierung fehlgeschlagen: {e}")

            st.markdown("---")

        if total_created > 0:
            board_url = f"https://miro.com/app/board/{board_id}/"
            st.success(f"🎉 **{len(ideas)} Videos** erfolgreich platziert!")
            st.markdown(
                f'<a href="{board_url}" target="_blank" '
                f'style="display:inline-block;background:#ffd02f;color:#1a1a2e;padding:12px 24px;'
                f'border-radius:8px;text-decoration:none;font-weight:700;margin-top:8px;">'
                f'🔗 Board öffnen</a>',
                unsafe_allow_html=True,
            )

        # Clear state after placement
        st.session_state.pop("video_ideas", None)
        st.session_state.pop("research", None)

st.markdown("<br><br>", unsafe_allow_html=True)
