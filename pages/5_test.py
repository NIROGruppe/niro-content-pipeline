import streamlit as st
import json
from datetime import datetime
from shared import inject_css

st.set_page_config(page_title="Trading Bots", page_icon="🔒", layout="wide")
inject_css()

# ─── PASSWORD GATE ───────────────────────────────────────────────────────────

def check_password():
    if "test_authenticated" not in st.session_state:
        st.session_state["test_authenticated"] = False
    if st.session_state["test_authenticated"]:
        return True

    st.markdown("""
    <div style="text-align:center; padding: 80px 0 20px 0;">
        <div style="font-size:48px;">🔒</div>
        <h2>Zugang geschützt</h2>
    </div>
    """, unsafe_allow_html=True)

    password = st.text_input("Passwort", type="password", key="test_pw_input")
    if st.button("Login", use_container_width=True, type="primary"):
        try:
            correct_pw = st.secrets["TEST_PAGE_PASSWORD"]
        except Exception:
            import os
            correct_pw = os.getenv("TEST_PAGE_PASSWORD", "")
        if password == correct_pw:
            st.session_state["test_authenticated"] = True
            st.rerun()
        else:
            st.error("Falsches Passwort.")
    return False

if not check_password():
    st.stop()


# ─── NAVIGATION STATE ────────────────────────────────────────────────────────

if "bot_view" not in st.session_state:
    st.session_state["bot_view"] = "landing"


# ═══════════════════════════════════════════════════════════════════════════════
# LANDING PAGE
# ═══════════════════════════════════════════════════════════════════════════════

def render_landing():
    st.markdown("""
    <div style="text-align:center;padding:40px 0 10px 0;">
        <div style="font-size:42px;font-weight:900;letter-spacing:-1px;">
            🤖 NIRO Trading Bots
        </div>
        <div style="font-size:16px;color:#888;margin-top:8px;">
            KI-gesteuerte Bots mit Survival Pressure System
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    col1, col2 = st.columns(2, gap="large")

    with col1:
        st.markdown("""
        <div style="background:linear-gradient(135deg, #0a0a1a, #1a1a2e);
                    border:2px solid #4a4ae8;border-radius:20px;padding:32px;
                    min-height:320px;">
            <div style="font-size:48px;text-align:center;">🎰</div>
            <div style="font-size:24px;font-weight:800;text-align:center;margin-top:12px;
                        color:#7a7aff;">Polymarket Bot</div>
            <div style="font-size:13px;color:#888;text-align:center;margin-top:8px;">
                Prediction Markets · Sentiment Analysis · Kelly Criterion
            </div>
            <div style="margin-top:20px;font-size:13px;color:#aaa;">
                <div style="padding:4px 0;">📡 Scannt Polymarket & Manifold</div>
                <div style="padding:4px 0;">🧠 Claude AI Sentiment + Predictions</div>
                <div style="padding:4px 0;">📊 Kelly Criterion Risk Management</div>
                <div style="padding:4px 0;">🧬 Survival Pressure System</div>
                <div style="padding:4px 0;">🔬 Auto-Postmortem bei Verlusten</div>
            </div>
            <div style="margin-top:16px;padding:8px;background:#4a4ae820;border-radius:8px;
                        text-align:center;font-size:12px;color:#f39c12;">
                ⏳ Wartet auf EU-Freigabe von Polymarket
            </div>
        </div>
        """, unsafe_allow_html=True)

        if st.button("🎰 Polymarket Bot öffnen", use_container_width=True, type="primary", key="open_poly"):
            st.session_state["bot_view"] = "polymarket"
            st.rerun()

    with col2:
        st.markdown("""
        <div style="background:linear-gradient(135deg, #0a1a0a, #1a2e1a);
                    border:2px solid #2ecc71;border-radius:20px;padding:32px;
                    min-height:320px;">
            <div style="font-size:48px;text-align:center;">📰</div>
            <div style="font-size:24px;font-weight:800;text-align:center;margin-top:12px;
                        color:#2ecc71;">Stock & News Bot</div>
            <div style="font-size:13px;color:#888;text-align:center;margin-top:8px;">
                Aktien-Signale · News-Sentiment · Trendanalyse
            </div>
            <div style="margin-top:20px;font-size:13px;color:#aaa;">
                <div style="padding:4px 0;">📈 Scannt Top-Aktien & Indizes</div>
                <div style="padding:4px 0;">📰 News-Sentiment via Reddit, RSS, Twitter</div>
                <div style="padding:4px 0;">🧠 Claude AI Analyse & Signale</div>
                <div style="padding:4px 0;">⚡ Buy/Sell/Hold Empfehlungen</div>
                <div style="padding:4px 0;">📊 Sektor-Heatmap & Trendübersicht</div>
            </div>
            <div style="margin-top:16px;padding:8px;background:#2ecc7120;border-radius:8px;
                        text-align:center;font-size:12px;color:#2ecc71;">
                ✅ Sofort nutzbar — Trade Journal mit Postmortem-Lernschleife
            </div>
        </div>
        """, unsafe_allow_html=True)

        if st.button("📰 Stock & News Bot öffnen", use_container_width=True, type="primary", key="open_stock"):
            st.session_state["bot_view"] = "stock"
            st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
# POLYMARKET BOT
# ═══════════════════════════════════════════════════════════════════════════════

def render_polymarket_bot():
    from trading_bot.db.database import (
        get_stats, get_flagged_markets, get_all_markets,
        get_open_trades, get_trade_history, get_all_trades,
        get_postmortems, get_recent_logs, get_settings,
    )
    from trading_bot.config import load_settings, save_settings, DEFAULTS
    from trading_bot.main import start_bot, stop_bot, is_bot_running, run_pipeline_once, settle_trade_manually
    from trading_bot.agents.survival import get_survival_status, STAGES
    from trading_bot.dashboard.components.charts import (
        pnl_line_chart, win_loss_bar_chart, confidence_distribution,
        edge_vs_pnl_scatter, postmortem_category_chart,
    )

    # Back button
    if st.button("← Zurück zur Übersicht", key="back_poly"):
        st.session_state["bot_view"] = "landing"
        st.rerun()

    st.markdown("# 🎰 Polymarket Trading Bot")
    st.markdown("---")

    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
        "📊 Overview", "🔍 Active Markets", "⚡ Live Trades",
        "📜 Trade History", "🔬 Postmortem", "⚙️ Settings", "🧬 Survival"
    ])

    # ── TAB 1: OVERVIEW ──
    with tab1:
        settings = load_settings()
        stats = get_stats()
        bot_running = is_bot_running()

        st.markdown('<div class="section-label">🤖 Bot Control</div>', unsafe_allow_html=True)
        ctrl_col1, ctrl_col2, ctrl_col3, ctrl_col4 = st.columns(4)

        with ctrl_col1:
            bot_status = settings.get("bot_status", "PAUSED")
            if bot_status == "RUNNING":
                status_color = "#2ecc71"
            elif bot_status == "DRY RUN":
                status_color = "#f39c12"
            else:
                status_color = "#e74c3c"
            st.markdown(
                f'<div style="background:#1e1e1e;border:2px solid {status_color};border-radius:12px;'
                f'padding:20px;text-align:center;">'
                f'<div style="font-size:12px;color:#888;">STATUS</div>'
                f'<div style="font-size:24px;font-weight:800;color:{status_color};">{bot_status}</div>'
                f'</div>', unsafe_allow_html=True
            )

        with ctrl_col2:
            if st.button("▶️ Start Bot", use_container_width=True, type="primary"):
                settings["bot_status"] = "DRY RUN" if settings.get("dry_run", True) else "RUNNING"
                save_settings(settings)
                start_bot()
                st.rerun()

        with ctrl_col3:
            if st.button("⏸️ Pause", use_container_width=True):
                settings["bot_status"] = "PAUSED"
                save_settings(settings)
                st.rerun()

        with ctrl_col4:
            if st.button("⏹️ Stop", use_container_width=True):
                settings["bot_status"] = "PAUSED"
                save_settings(settings)
                stop_bot()
                st.rerun()

        st.markdown("<br>", unsafe_allow_html=True)

        dry_run = st.toggle("🧪 Dry Run Mode", value=settings.get("dry_run", True))
        if dry_run != settings.get("dry_run", True):
            settings["dry_run"] = dry_run
            if bot_running:
                settings["bot_status"] = "DRY RUN" if dry_run else "RUNNING"
            save_settings(settings)
            st.rerun()

        if st.button("🔄 Run Pipeline Once", use_container_width=True):
            with st.spinner("Running pipeline..."):
                run_pipeline_once()
            st.success("Pipeline run complete!")
            st.rerun()

        st.markdown("---")

        # Survival Status
        survival = get_survival_status()
        st.markdown(
            f'<div style="background:linear-gradient(135deg, #0a0a0a, #1a1a1a);border:2px solid {survival["stage_color"]};'
            f'border-radius:16px;padding:24px;margin-bottom:20px;">'
            f'<div style="display:flex;justify-content:space-between;align-items:center;">'
            f'<div>'
            f'<div style="font-size:14px;color:#888;">SURVIVAL STAGE</div>'
            f'<div style="font-size:32px;font-weight:900;color:{survival["stage_color"]};">'
            f'{survival["stage_emoji"]} {survival["stage_name"]}</div>'
            f'<div style="font-size:12px;color:#666;margin-top:4px;">{survival["stage_description"]}</div>'
            f'</div>'
            f'<div style="text-align:right;">'
            f'<div style="font-size:14px;color:#888;">BANKROLL</div>'
            f'<div style="font-size:28px;font-weight:800;color:white;">${survival["current_bankroll"]:,.2f}</div>'
            f'<div style="font-size:12px;color:#888;">{survival["ratio"]:.1f}x Start · {survival["progress_to_goal"]:.1f}% to Goal</div>'
            f'</div></div></div>',
            unsafe_allow_html=True
        )

        progress_pct = min(survival["progress_to_goal"] / 100, 1.0)
        st.markdown(
            f'<div style="background:#1a1a1a;border-radius:8px;height:24px;margin-bottom:20px;overflow:hidden;">'
            f'<div style="background:linear-gradient(90deg, {survival["stage_color"]}, #FFD700);'
            f'width:{max(progress_pct * 100, 1):.1f}%;height:100%;border-radius:8px;'
            f'display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:700;'
            f'color:#000;">${survival["current_bankroll"]:.0f} / ${survival["goal"]:.0f}</div></div>',
            unsafe_allow_html=True
        )

        st.markdown("---")
        st.markdown('<div class="section-label">📊 Performance</div>', unsafe_allow_html=True)

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("💰 Bankroll", f"${survival['current_bankroll']:,.2f}")
        m2.metric("📈 Today P&L", f"${stats['today_pnl']:+,.2f}", delta=f"{stats['today_pnl']:+,.2f}")
        m3.metric("🎯 Win Rate", f"{stats['win_rate']}%", delta=f"{stats['wins']}W / {stats['losses']}L")
        m4.metric("📊 Total Trades", stats["total_trades"], delta=f"{stats['open_trades']} open")

        m5, m6 = st.columns(2)
        m5.metric("💵 Total P&L", f"${stats['total_pnl']:+,.2f}")
        m6.metric("📂 Open Trades", stats["open_trades"])

        st.markdown("---")
        st.markdown('<div class="section-label">📋 Recent Activity</div>', unsafe_allow_html=True)
        logs = get_recent_logs(20)
        if logs:
            for log in logs[:10]:
                level = log.get("level", "INFO")
                icon = {"INFO": "ℹ️", "WARN": "⚠️", "ERROR": "❌", "DEBUG": "🔍"}.get(level, "📌")
                st.markdown(
                    f'<div style="font-size:12px;color:#888;padding:4px 0;">'
                    f'{icon} <b>[{log.get("agent", "?")}]</b> {log.get("message", "")} '
                    f'<span style="color:#555;">{log.get("created_at", "")[:19]}</span></div>',
                    unsafe_allow_html=True
                )
        else:
            st.info("No activity yet. Start the bot or run the pipeline manually.")

    # ── TAB 2: ACTIVE MARKETS ──
    with tab2:
        st.markdown('<div class="section-label">🔍 Flagged Markets</div>', unsafe_allow_html=True)
        markets = get_flagged_markets()
        if markets:
            for m in markets:
                flag = m.get("flagged_reason", "")
                liquidity = m.get("liquidity", 0)
                volume = m.get("volume_24h", 0)
                price = m.get("price_yes", 0.5)
                spread = m.get("spread", 0)
                border_color = "#2ecc71" if volume > 50000 else "#f39c12" if volume > 10000 else "#e74c3c"

                st.markdown(
                    f'<div style="background:#1e1e1e;border-left:4px solid {border_color};'
                    f'border-radius:8px;padding:16px;margin-bottom:12px;">'
                    f'<div style="font-weight:700;font-size:14px;">{m.get("question", "?")}</div>'
                    f'<div style="font-size:12px;color:#888;margin-top:6px;">'
                    f'💧 ${liquidity:,.0f} · 📊 ${volume:,.0f}/24h · '
                    f'💰 YES {price:.1%} · Spread {spread:.1%} · '
                    f'<span style="color:{border_color};">{flag}</span>'
                    f'</div></div>',
                    unsafe_allow_html=True
                )
        else:
            st.info("No flagged markets. Run the scan agent to find opportunities.")

        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown('<div class="section-label">📋 All Scanned Markets</div>', unsafe_allow_html=True)
        all_markets = get_all_markets()
        if all_markets:
            import pandas as pd
            df = pd.DataFrame(all_markets)[["question", "liquidity", "volume_24h", "price_yes", "spread", "flagged_reason", "scanned_at"]]
            df.columns = ["Market", "Liquidity", "Volume 24h", "Price (YES)", "Spread", "Flag", "Scanned"]
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("No markets scanned yet.")

    # ── TAB 3: LIVE TRADES ──
    with tab3:
        st.markdown('<div class="section-label">⚡ Open Positions</div>', unsafe_allow_html=True)
        open_trades = get_open_trades()
        if open_trades:
            for t in open_trades:
                entry = t.get("entry_price", 0)
                current = t.get("current_price", entry)
                size = t.get("size", 0)
                unrealized = (current - entry) * size / entry if entry > 0 else 0
                pnl_color = "#2ecc71" if unrealized >= 0 else "#e74c3c"
                st.markdown(
                    f'<div style="background:#1e1e1e;border:1px solid #2a2a2a;border-radius:12px;padding:16px;margin-bottom:12px;">'
                    f'<div style="font-weight:700;">{t.get("market_question", "?")}</div>'
                    f'<div style="margin-top:8px;font-size:13px;">'
                    f'<span class="platform-badge">{t.get("position", "?")}</span> '
                    f'Entry: {entry:.1%} · Current: {current:.1%} · Size: ${size:.2f} · '
                    f'<span style="color:{pnl_color};font-weight:700;">P&L: ${unrealized:+,.2f}</span>'
                    f' · Edge: {t.get("edge", 0):.1%} · Conf: {t.get("confidence", 0):.0f}%'
                    f'{"  🧪 DRY RUN" if t.get("dry_run") else ""}'
                    f'</div></div>',
                    unsafe_allow_html=True
                )
                sc1, sc2 = st.columns(2)
                with sc1:
                    if st.button(f"✅ Won", key=f"win_{t['id']}"):
                        settle_trade_manually(t["id"], "won")
                        st.rerun()
                with sc2:
                    if st.button(f"❌ Lost", key=f"lose_{t['id']}"):
                        settle_trade_manually(t["id"], "lost")
                        st.rerun()
        else:
            st.info("No open positions.")

    # ── TAB 4: TRADE HISTORY ──
    with tab4:
        st.markdown('<div class="section-label">📜 Closed Trades</div>', unsafe_allow_html=True)
        all_trades = get_all_trades()
        closed_trades = [t for t in all_trades if t.get("status") in ("settled", "blocked")]
        if closed_trades:
            settled = [t for t in closed_trades if t["status"] == "settled"]
            s1, s2, s3, s4 = st.columns(4)
            total_profit = sum(t.get("pnl", 0) for t in settled)
            avg_edge = sum(t.get("edge", 0) for t in settled) / max(len(settled), 1)
            avg_conf = sum(t.get("confidence", 0) for t in settled) / max(len(settled), 1)
            s1.metric("💵 Total Profit", f"${total_profit:+,.2f}")
            s2.metric("📐 Avg Edge", f"{avg_edge:.1%}")
            s3.metric("🎯 Avg Confidence", f"{avg_conf:.0f}%")
            s4.metric("📊 Settled", len(settled))
            st.markdown("<br>", unsafe_allow_html=True)

            chart_col1, chart_col2 = st.columns(2)
            with chart_col1:
                st.plotly_chart(pnl_line_chart(settled), use_container_width=True)
            with chart_col2:
                st.plotly_chart(win_loss_bar_chart(all_trades), use_container_width=True)

            st.markdown("<br>", unsafe_allow_html=True)
            for t in closed_trades[:50]:
                pnl = t.get("pnl", 0)
                status = t.get("status", "?")
                if status == "blocked":
                    icon, color = "🚫", "#f39c12"
                elif pnl > 0:
                    icon, color = "✅", "#2ecc71"
                elif pnl < 0:
                    icon, color = "❌", "#e74c3c"
                else:
                    icon, color = "➖", "#888"
                block_reason = f" — {t.get('block_reason', '')}" if t.get("block_reason") else ""
                st.markdown(
                    f'<div style="font-size:13px;padding:6px 0;border-bottom:1px solid #1e1e1e;">'
                    f'{icon} <b>{t.get("market_question", "?")[:60]}</b> '
                    f'<span style="color:{color};font-weight:700;">${pnl:+,.2f}</span> '
                    f'{t.get("position", "")} @ {t.get("entry_price", 0):.1%} · '
                    f'${t.get("size", 0):.2f}{block_reason}</div>',
                    unsafe_allow_html=True
                )
        else:
            st.info("No trade history yet.")

    # ── TAB 5: POSTMORTEM ──
    with tab5:
        st.markdown('<div class="section-label">🔬 Loss Postmortems</div>', unsafe_allow_html=True)
        postmortems = get_postmortems()
        if postmortems:
            st.plotly_chart(postmortem_category_chart(postmortems), use_container_width=True)
            st.markdown("<br>", unsafe_allow_html=True)
            for pm in postmortems:
                with st.expander(
                    f"Trade #{pm.get('trade_id', '?')} — {pm.get('market_question', '?')[:60]} "
                    f"(Loss: ${pm.get('loss_amount', 0):.2f})"
                ):
                    st.markdown(f"**What went wrong:** {pm.get('what_went_wrong', '–')}")
                    st.markdown(f"**Pattern detected:** {pm.get('pattern_detected', '–')}")
                    param_changes = pm.get("parameter_changes", "{}")
                    if isinstance(param_changes, str):
                        try:
                            param_changes = json.loads(param_changes)
                        except Exception:
                            param_changes = {}
                    if param_changes:
                        st.markdown("**Parameter changes:**")
                        for param, change in param_changes.items():
                            if isinstance(change, dict):
                                st.markdown(
                                    f"- `{param}`: {change.get('current')} → {change.get('suggested')} "
                                    f"({change.get('reason', '')})"
                                )
                    st.markdown(f"*{pm.get('created_at', '')}*")
        else:
            st.info("No postmortems yet. Postmortems are generated automatically after losing trades.")

    # ── TAB 6: SETTINGS ──
    with tab6:
        st.markdown('<div class="section-label">⚙️ Bot Parameters</div>', unsafe_allow_html=True)
        settings = load_settings()
        with st.form("settings_form"):
            st.markdown("**Scan Agent**")
            sc1, sc2 = st.columns(2)
            with sc1:
                min_liquidity = st.number_input("Min Liquidity ($)", value=int(settings.get("min_liquidity", 10000)), step=1000)
                min_volume = st.number_input("Min 24h Volume ($)", value=int(settings.get("min_volume_24h", 1000)), step=500)
            with sc2:
                scan_interval = st.number_input("Scan Interval (seconds)", value=int(settings.get("scan_interval_seconds", 300)), step=60)

            st.markdown("---")
            st.markdown("**Prediction Agent**")
            confidence_threshold = st.slider("Min Confidence (%)", 0, 100, int(settings.get("confidence_threshold", 70)))

            st.markdown("---")
            st.markdown("**Risk Agent**")
            rc1, rc2, rc3 = st.columns(3)
            with rc1:
                kelly_fraction = st.slider("Kelly Fraction", 0.05, 1.0, float(settings.get("kelly_fraction", 0.25)), 0.05)
            with rc2:
                max_bet = st.slider("Max Bet (% bankroll)", 1, 25, int(settings.get("max_bet_pct", 0.05) * 100))
            with rc3:
                min_edge = st.slider("Min Edge (%)", 1, 30, int(settings.get("min_edge", 0.05) * 100))

            st.markdown("---")
            st.markdown("**Bankroll & Survival**")
            bc1, bc2 = st.columns(2)
            with bc1:
                bankroll = st.number_input("Starting Bankroll ($)", value=float(settings.get("starting_bankroll", 20.0)), step=5.0)
            with bc2:
                goal = st.number_input("Goal ($)", value=float(settings.get("bankroll_goal", 1000.0)), step=100.0)

            st.info("⚠️ Kelly, Max Bet, Min Edge, and Confidence are **base values**. "
                    "The Survival System overrides them automatically based on bankroll health.")

            submitted = st.form_submit_button("💾 Save Settings", use_container_width=True, type="primary")
            if submitted:
                new_settings = {
                    "min_liquidity": min_liquidity,
                    "min_volume_24h": min_volume,
                    "scan_interval_seconds": scan_interval,
                    "confidence_threshold": confidence_threshold,
                    "kelly_fraction": kelly_fraction,
                    "max_bet_pct": max_bet / 100,
                    "min_edge": min_edge / 100,
                    "initial_bankroll": bankroll,
                    "starting_bankroll": bankroll,
                    "bankroll_goal": goal,
                    "dry_run": settings.get("dry_run", True),
                    "bot_status": settings.get("bot_status", "PAUSED"),
                }
                save_settings(new_settings)
                st.success("Settings saved!")
                st.rerun()

        st.markdown("---")
        st.markdown('<div class="section-label">🔑 API Status</div>', unsafe_allow_html=True)
        import os
        def _check_key(key):
            try:
                val = st.secrets.get(key, "")
            except Exception:
                val = os.getenv(key, "")
            return bool(val)

        apis = {
            "ANTHROPIC_API_KEY": "Claude API",
            "POLYMARKET_API_KEY": "Polymarket",
            "TWITTER_BEARER_TOKEN": "Twitter/X",
            "REDDIT_CLIENT_ID": "Reddit",
        }
        for key, name in apis.items():
            connected = _check_key(key)
            icon = "🟢" if connected else "🔴"
            st.markdown(f"{icon} **{name}** — {'Connected' if connected else 'Not configured'}")

    # ── TAB 7: SURVIVAL ──
    with tab7:
        survival = get_survival_status()
        st.markdown('<div class="section-label">🧬 Survival Pressure System</div>', unsafe_allow_html=True)
        st.markdown(
            f"Starting with **${survival['starting_bankroll']:.0f}**, "
            f"goal is **${survival['goal']:,.0f}** — "
            f"a **{survival['goal'] / survival['starting_bankroll']:.0f}x** return."
        )
        st.markdown("<br>", unsafe_allow_html=True)

        st.markdown(
            f'<div style="background:linear-gradient(135deg, #0a0a0a, #1a1a1a);border:3px solid {survival["stage_color"]};'
            f'border-radius:16px;padding:32px;text-align:center;margin-bottom:24px;">'
            f'<div style="font-size:48px;">{survival["stage_emoji"]}</div>'
            f'<div style="font-size:28px;font-weight:900;color:{survival["stage_color"]};margin-top:8px;">'
            f'{survival["stage_name"]}</div>'
            f'<div style="font-size:16px;color:#888;margin-top:8px;">{survival["stage_description"]}</div>'
            f'<div style="margin-top:16px;font-size:14px;color:#aaa;">'
            f'Bankroll: <b>${survival["current_bankroll"]:,.2f}</b> · '
            f'Ratio: <b>{survival["ratio"]:.2f}x</b> · '
            f'Progress: <b>{survival["progress_to_goal"]:.1f}%</b>'
            f'</div></div>',
            unsafe_allow_html=True
        )

        st.markdown('<div class="section-label">📐 Active Parameters (Survival-Adjusted)</div>', unsafe_allow_html=True)
        p1, p2, p3, p4 = st.columns(4)
        p1.metric("Kelly Fraction", f"{survival['kelly_fraction']:.2f}")
        p2.metric("Max Bet", f"{survival['max_bet_pct']:.0%}")
        p3.metric("Min Edge", f"{survival['min_edge']:.0%}")
        p4.metric("Min Confidence", f"{survival['confidence_threshold']}%")

        st.markdown("---")
        st.markdown('<div class="section-label">📊 All Stages</div>', unsafe_allow_html=True)

        for i, stage in enumerate(STAGES):
            is_active = stage["name"] == survival["stage_name"]
            border = f"3px solid {stage['color']}" if is_active else "1px solid #2a2a2a"
            bg = "#1a1a1a" if is_active else "#111"
            glow = f"box-shadow: 0 0 20px {stage['color']}40;" if is_active else ""

            bankroll_low = stage["min_ratio"] * survival["starting_bankroll"]
            bankroll_high = stage["max_ratio"] * survival["starting_bankroll"] if stage["max_ratio"] != float("inf") else "∞"
            bankroll_range = f"${bankroll_low:.0f} – {'$' + f'{bankroll_high:.0f}' if isinstance(bankroll_high, float) else bankroll_high}"
            active_label = ' <span style="color:#FFD700;font-weight:900;"> ← YOU ARE HERE</span>' if is_active else ""

            st.markdown(
                f'<div style="background:{bg};border:{border};border-radius:12px;'
                f'padding:16px;margin-bottom:8px;{glow}">'
                f'<div style="display:flex;justify-content:space-between;align-items:center;">'
                f'<div>'
                f'<span style="font-size:20px;">{stage["emoji"]}</span> '
                f'<span style="font-size:16px;font-weight:800;color:{stage["color"]};">{stage["name"]}</span>'
                f'{active_label}'
                f'<div style="font-size:12px;color:#666;margin-top:4px;">{stage["description"]}</div>'
                f'</div>'
                f'<div style="text-align:right;font-size:12px;color:#888;">'
                f'<div>{bankroll_range}</div>'
                f'<div>Kelly: {stage["kelly_fraction"]:.2f} · '
                f'Max Bet: {stage["max_bet_pct"]:.0%} · '
                f'Min Edge: {stage["min_edge"]:.0%} · '
                f'Conf: {stage["confidence_threshold"]}%</div>'
                f'</div></div></div>',
                unsafe_allow_html=True
            )

        st.markdown("---")
        if survival["next_stage_at"]:
            needed = survival["next_stage_at"] - survival["current_bankroll"]
            if needed > 0:
                next_stage = STAGES[survival["stage_index"] + 1]
                st.markdown(
                    f"**Next stage:** {next_stage['emoji']} **{next_stage['name']}** "
                    f"at **${survival['next_stage_at']:.2f}** "
                    f"(need **${needed:.2f}** more)"
                )
        else:
            st.markdown("**You're at the highest stage! Push to $1,000!**")


# ═══════════════════════════════════════════════════════════════════════════════
# STOCK & NEWS BOT
# ═══════════════════════════════════════════════════════════════════════════════

def render_stock_bot():
    from stock_bot.db.database import (
        init_db as stock_init_db, get_stats as stock_stats,
        get_watchlist, add_ticker, remove_ticker,
        get_signals, get_all_latest_sentiments,
        get_open_trades as stock_open_trades, get_closed_trades,
        get_all_trades as stock_all_trades, insert_trade as stock_insert_trade,
        get_postmortems as stock_postmortems, get_recent_logs as stock_logs,
        get_underdogs, get_recent_underdogs,
    )
    from stock_bot.config import load_settings as stock_load_settings, save_settings as stock_save_settings
    from stock_bot.main import run_scan_once, run_underdog_scan, close_trade_with_postmortem, start_bot as stock_start, stop_bot as stock_stop, is_bot_running as stock_running

    stock_init_db()

    if st.button("← Zurück zur Übersicht", key="back_stock"):
        st.session_state["bot_view"] = "landing"
        st.rerun()

    st.markdown("# 📰 Stock & News Bot")
    st.markdown("---")

    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
        "📊 Overview", "📰 Signals", "📒 Trade Journal",
        "🔬 Postmortems", "🔥 Underdogs", "📋 News Feed", "⚙️ Settings"
    ])

    # ── TAB 1: OVERVIEW ──
    with tab1:
        settings = stock_load_settings()
        stats = stock_stats()

        # Bot controls
        st.markdown('<div class="section-label">🤖 Bot Control</div>', unsafe_allow_html=True)
        c1, c2, c3, c4 = st.columns(4)

        with c1:
            bot_status = settings.get("bot_status", "PAUSED")
            sc = "#2ecc71" if bot_status == "RUNNING" else "#e74c3c"
            st.markdown(
                f'<div style="background:#1e1e1e;border:2px solid {sc};border-radius:12px;'
                f'padding:20px;text-align:center;">'
                f'<div style="font-size:12px;color:#888;">STATUS</div>'
                f'<div style="font-size:24px;font-weight:800;color:{sc};">{bot_status}</div>'
                f'</div>', unsafe_allow_html=True)

        with c2:
            if st.button("▶️ Start", use_container_width=True, type="primary", key="stock_start"):
                settings["bot_status"] = "RUNNING"
                stock_save_settings(settings)
                stock_start()
                st.rerun()

        with c3:
            if st.button("⏹️ Stop", use_container_width=True, key="stock_stop"):
                settings["bot_status"] = "PAUSED"
                stock_save_settings(settings)
                stock_stop()
                st.rerun()

        with c4:
            if st.button("🔄 Scan Now", use_container_width=True, key="stock_scan"):
                with st.spinner("Scanning all tickers..."):
                    run_scan_once()
                st.success("Scan complete!")
                st.rerun()

        st.markdown("---")

        # Stats
        st.markdown('<div class="section-label">📊 Performance</div>', unsafe_allow_html=True)
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("💵 Total P&L", f"${stats['total_pnl']:+,.2f}")
        m2.metric("🎯 Win Rate", f"{stats['win_rate']}%",
                  delta=f"{stats['wins']}W / {stats['losses']}L")
        m3.metric("📊 Total Trades", stats["total_trades"],
                  delta=f"{stats['open_trades']} open")
        m4.metric("📈 Today P&L", f"${stats['today_pnl']:+,.2f}")

        st.markdown("---")

        # Latest signals
        st.markdown('<div class="section-label">📰 Latest Signals</div>', unsafe_allow_html=True)
        signals = get_signals(10)
        if signals:
            for s in signals[:8]:
                d = s.get("direction", "HOLD")
                emoji = {"BUY": "🟢", "SELL": "🔴", "HOLD": "⚪"}.get(d, "⚪")
                strength_color = {"STRONG": "#2ecc71", "MODERATE": "#f39c12", "WEAK": "#888"}.get(s.get("strength", ""), "#888")

                pos = s.get("position_type", "")
                hold = s.get("hold_duration", "")
                chk = s.get("check_interval", "")
                pos_color = "#2ecc71" if "LONG" in (pos or "") else "#e74c3c" if "SHORT" in (pos or "") else "#888"

                detail_row = ""
                if pos and pos != "—":
                    detail_row = (
                        f'<div style="display:flex;gap:16px;margin-top:6px;flex-wrap:wrap;">'
                        f'<span style="font-size:12px;"><span style="color:{pos_color};font-weight:700;">{pos}</span></span>'
                    )
                    if hold and hold != "—":
                        detail_row += f'<span style="font-size:12px;color:#888;">⏱ {hold}</span>'
                    if chk and chk != "—":
                        detail_row += f'<span style="font-size:12px;color:#888;">👁 {chk}</span>'
                    detail_row += '</div>'

                st.markdown(
                    f'<div style="background:#1e1e1e;border-left:4px solid {strength_color};'
                    f'border-radius:8px;padding:12px 16px;margin-bottom:8px;">'
                    f'<div style="display:flex;justify-content:space-between;">'
                    f'<div><b>{s.get("ticker", "?")}</b> {emoji} <b>{d}</b> '
                    f'<span style="color:{strength_color};">({s.get("strength", "?")})</span></div>'
                    f'<div style="color:#888;">@ ${s.get("price_at_signal", 0):.2f}</div></div>'
                    + detail_row
                    + f'<div style="font-size:12px;color:#666;margin-top:4px;">{s.get("reasoning", "")[:150]}</div>'
                    f'<div style="font-size:11px;color:#555;margin-top:2px;">{s.get("created_at", "")[:19]}</div>'
                    f'</div>',
                    unsafe_allow_html=True
                )
        else:
            st.info("Keine Signale vorhanden. Klicke 'Scan Now' für den ersten Scan.")

    # ── TAB 2: SIGNALS ──
    with tab2:
        st.markdown('<div class="section-label">📰 Signal History</div>', unsafe_allow_html=True)

        # Sentiment overview
        sentiments = get_all_latest_sentiments()
        if sentiments:
            st.markdown("**Aktuelles Sentiment pro Ticker:**")
            cols = st.columns(min(len(sentiments), 5))
            for i, sent in enumerate(sentiments[:10]):
                score = sent.get("sentiment_score", 0)
                if score > 0.3:
                    color, label = "#2ecc71", "BULLISH"
                elif score < -0.3:
                    color, label = "#e74c3c", "BEARISH"
                else:
                    color, label = "#f39c12", "NEUTRAL"

                with cols[i % 5]:
                    st.markdown(
                        f'<div style="background:#1e1e1e;border:1px solid {color};border-radius:8px;'
                        f'padding:12px;text-align:center;margin-bottom:8px;">'
                        f'<div style="font-weight:800;">{sent.get("ticker", "?")}</div>'
                        f'<div style="color:{color};font-size:20px;font-weight:700;">{score:+.2f}</div>'
                        f'<div style="font-size:11px;color:#888;">{label}</div>'
                        f'</div>',
                        unsafe_allow_html=True
                    )

        st.markdown("---")

        # Full signal list
        all_signals = get_signals(50)
        if all_signals:
            import pandas as pd
            cols = ["ticker", "direction", "strength", "position_type", "hold_duration",
                    "check_interval", "sentiment_score", "price_at_signal", "reasoning", "created_at"]
            # Only use columns that exist in data
            available = [c for c in cols if c in all_signals[0]]
            df = pd.DataFrame(all_signals)[available]
            col_names = {
                "ticker": "Ticker", "direction": "Signal", "strength": "Strength",
                "position_type": "Position", "hold_duration": "Haltedauer",
                "check_interval": "Check-Intervall", "sentiment_score": "Sentiment",
                "price_at_signal": "Price", "reasoning": "Reasoning", "created_at": "Time"
            }
            df.columns = [col_names.get(c, c) for c in available]
            st.dataframe(df, use_container_width=True, hide_index=True)

    # ── TAB 3: TRADE JOURNAL ──
    with tab3:
        st.markdown('<div class="section-label">📒 Trade Journal</div>', unsafe_allow_html=True)

        # Log new trade
        with st.expander("➕ Neuen Trade eintragen", expanded=False):
            with st.form("new_trade_form"):
                tc1, tc2 = st.columns(2)
                with tc1:
                    trade_ticker = st.text_input("Ticker", placeholder="AAPL").upper()
                    trade_direction = st.selectbox("Richtung", ["LONG", "SHORT"])
                with tc2:
                    trade_entry = st.number_input("Entry Price ($)", min_value=0.01, step=0.01)
                    trade_size = st.number_input("Anzahl Aktien", min_value=0.01, step=1.0, value=1.0)

                trade_notes = st.text_area("Notizen (optional)", placeholder="Warum diesen Trade?")

                if st.form_submit_button("💾 Trade speichern", use_container_width=True, type="primary"):
                    if trade_ticker and trade_entry > 0:
                        tid = stock_insert_trade({
                            "ticker": trade_ticker,
                            "direction": trade_direction,
                            "entry_price": trade_entry,
                            "size": trade_size,
                            "notes": trade_notes,
                        })
                        st.success(f"Trade #{tid} gespeichert!")
                        st.rerun()

        # Open trades
        st.markdown("---")
        st.markdown("**Offene Trades:**")
        open_trades = stock_open_trades()
        if open_trades:
            for t in open_trades:
                pnl_color = "#888"
                st.markdown(
                    f'<div style="background:#1e1e1e;border:1px solid #2a2a2a;border-radius:12px;'
                    f'padding:16px;margin-bottom:12px;">'
                    f'<div style="font-weight:700;">'
                    f'{"🟢" if t["direction"] == "LONG" else "🔴"} '
                    f'{t.get("ticker", "?")} — {t.get("direction", "?")} '
                    f'@ ${t.get("entry_price", 0):.2f} × {t.get("size", 0):.1f}</div>'
                    f'<div style="font-size:12px;color:#888;margin-top:4px;">'
                    f'{t.get("notes", "") or "Keine Notizen"} · '
                    f'Eröffnet: {t.get("opened_at", "")[:10]}</div>'
                    f'</div>',
                    unsafe_allow_html=True
                )

                cc1, cc2 = st.columns([3, 1])
                with cc1:
                    exit_price = st.number_input(
                        f"Exit Price für #{t['id']}", min_value=0.01, step=0.01,
                        key=f"exit_{t['id']}", value=t.get("entry_price", 0.01)
                    )
                with cc2:
                    st.markdown("<br>", unsafe_allow_html=True)
                    if st.button(f"Trade schließen", key=f"close_{t['id']}"):
                        result = close_trade_with_postmortem(t["id"], exit_price)
                        if result.get("pnl", 0) >= 0:
                            st.success(f"Gewinn: ${result['pnl']:+,.2f}")
                        else:
                            st.error(f"Verlust: ${result['pnl']:+,.2f} — Postmortem wird erstellt...")
                        st.rerun()
        else:
            st.info("Keine offenen Trades.")

        # Closed trades
        st.markdown("---")
        st.markdown("**Geschlossene Trades:**")
        closed = get_closed_trades()
        if closed:
            for t in closed[:20]:
                pnl = t.get("pnl", 0)
                icon = "✅" if pnl > 0 else "❌" if pnl < 0 else "➖"
                color = "#2ecc71" if pnl > 0 else "#e74c3c" if pnl < 0 else "#888"
                st.markdown(
                    f'<div style="font-size:13px;padding:6px 0;border-bottom:1px solid #1e1e1e;">'
                    f'{icon} <b>{t.get("ticker", "?")}</b> {t.get("direction", "")} '
                    f'${t.get("entry_price", 0):.2f} → ${t.get("exit_price", 0):.2f} '
                    f'× {t.get("size", 0):.1f} '
                    f'<span style="color:{color};font-weight:700;">P&L: ${pnl:+,.2f}</span>'
                    f'</div>',
                    unsafe_allow_html=True
                )
        else:
            st.info("Noch keine geschlossenen Trades.")

    # ── TAB 4: POSTMORTEMS ──
    with tab4:
        st.markdown('<div class="section-label">🔬 Loss Postmortems</div>', unsafe_allow_html=True)
        postmortems = stock_postmortems()
        if postmortems:
            for pm in postmortems:
                with st.expander(
                    f"Trade #{pm.get('trade_id', '?')} — {pm.get('ticker', '?')} "
                    f"(Verlust: ${pm.get('loss_amount', 0):.2f})"
                ):
                    st.markdown(f"**Was schief lief:** {pm.get('what_went_wrong', '–')}")
                    st.markdown(f"**Pattern:** {pm.get('pattern_detected', '–')}")

                    lessons = pm.get("lessons_learned", "[]")
                    if isinstance(lessons, str):
                        try:
                            lessons = json.loads(lessons)
                        except Exception:
                            lessons = []
                    if lessons:
                        st.markdown("**Learnings:**")
                        for lesson in lessons:
                            st.markdown(f"- {lesson}")

                    param_changes = pm.get("parameter_changes", "{}")
                    if isinstance(param_changes, str):
                        try:
                            param_changes = json.loads(param_changes)
                        except Exception:
                            param_changes = {}
                    if param_changes:
                        st.markdown("**Parameter-Anpassungen:**")
                        for param, change in param_changes.items():
                            if isinstance(change, dict):
                                st.markdown(
                                    f"- `{param}`: {change.get('current')} → {change.get('suggested')} "
                                    f"({change.get('reason', '')})"
                                )

                    st.markdown(f"*{pm.get('created_at', '')}*")
        else:
            st.info("Keine Postmortems. Werden automatisch nach Verlust-Trades erstellt.")

    # ── TAB 5: UNDERDOGS ──
    with tab5:
        st.markdown('<div class="section-label">🔥 Underdog Scanner</div>', unsafe_allow_html=True)
        st.markdown("*Small/Mid-Cap Stocks mit Momentum — unter dem Radar, aber im Aufwind*")

        uc1, uc2 = st.columns([3, 1])
        with uc2:
            if st.button("🔍 Underdog Scan starten", use_container_width=True, key="underdog_scan"):
                with st.spinner("Scanning Reddit & checking volume..."):
                    run_underdog_scan()
                st.success("Underdog Scan abgeschlossen!")
                st.rerun()

        with uc1:
            time_filter = st.selectbox("Zeitraum", ["Letzte 7 Tage", "Letzte 30 Tage", "Alle"], key="ud_filter")

        st.markdown("---")

        if time_filter == "Letzte 7 Tage":
            underdogs = get_recent_underdogs(7)
        elif time_filter == "Letzte 30 Tage":
            underdogs = get_recent_underdogs(30)
        else:
            underdogs = get_underdogs(50)

        if underdogs:
            for i, ud in enumerate(underdogs):
                score = ud.get("score", 0)
                vol_ratio = ud.get("volume_ratio", 1.0)
                sentiment = ud.get("sentiment_score", 0)
                mentions = ud.get("reddit_mentions", 0)
                catalyst = ud.get("catalyst", "")
                cap_b = (ud.get("market_cap", 0) or 0) / 1e9

                # Score color
                if score >= 60:
                    score_color = "#2ecc71"
                    score_label = "HOT"
                elif score >= 40:
                    score_color = "#f39c12"
                    score_label = "WARM"
                else:
                    score_color = "#888"
                    score_label = "COOL"

                # Sentiment color
                if sentiment > 0.3:
                    sent_color = "#2ecc71"
                elif sentiment < -0.3:
                    sent_color = "#e74c3c"
                else:
                    sent_color = "#f39c12"

                ud_pos = ud.get("position_type", "") or ""
                ud_hold = ud.get("hold_duration", "") or ""
                ud_chk = ud.get("check_interval", "") or ""

                # Volume ratio indicator
                if vol_ratio >= 5:
                    vol_label = "🔥🔥🔥"
                elif vol_ratio >= 3:
                    vol_label = "🔥🔥"
                elif vol_ratio >= 2:
                    vol_label = "🔥"
                else:
                    vol_label = ""

                st.markdown(
                    f'<div style="background:linear-gradient(135deg, #0a0a1a, #1a1a2e);'
                    f'border:1px solid {score_color};border-radius:12px;padding:20px;margin-bottom:12px;">'
                    f'<div style="display:flex;justify-content:space-between;align-items:center;">'
                    f'<div>'
                    f'<span style="font-size:20px;font-weight:900;">{ud.get("ticker", "?")}</span> '
                    f'<span style="color:#888;font-size:14px;">{ud.get("name", "")}</span>'
                    f'</div>'
                    f'<div style="background:{score_color}20;border:1px solid {score_color};'
                    f'border-radius:20px;padding:4px 14px;">'
                    f'<span style="color:{score_color};font-weight:800;font-size:16px;">'
                    f'{score:.0f}</span>'
                    f'<span style="color:{score_color};font-size:11px;margin-left:4px;">{score_label}</span>'
                    f'</div>'
                    f'</div>'
                    f'<div style="display:flex;gap:24px;margin-top:12px;flex-wrap:wrap;">'
                    f'<div style="text-align:center;">'
                    f'<div style="font-size:11px;color:#666;">PRICE</div>'
                    f'<div style="font-size:16px;font-weight:700;">${ud.get("price", 0):.2f}</div>'
                    f'</div>'
                    f'<div style="text-align:center;">'
                    f'<div style="font-size:11px;color:#666;">MKT CAP</div>'
                    f'<div style="font-size:16px;font-weight:700;">${cap_b:.1f}B</div>'
                    f'</div>'
                    f'<div style="text-align:center;">'
                    f'<div style="font-size:11px;color:#666;">VOL RATIO</div>'
                    f'<div style="font-size:16px;font-weight:700;">{vol_ratio:.1f}x {vol_label}</div>'
                    f'</div>'
                    f'<div style="text-align:center;">'
                    f'<div style="font-size:11px;color:#666;">REDDIT</div>'
                    f'<div style="font-size:16px;font-weight:700;">{mentions} mentions</div>'
                    f'</div>'
                    f'<div style="text-align:center;">'
                    f'<div style="font-size:11px;color:#666;">SENTIMENT</div>'
                    f'<div style="font-size:16px;font-weight:700;color:{sent_color};">{sentiment:+.2f}</div>'
                    f'</div>'
                    f'</div>'
                    + (f'<div style="margin-top:12px;padding:10px;background:#ffffff08;border-radius:8px;font-size:13px;color:#aaa;"><b>Catalyst:</b> {catalyst}</div>' if catalyst else '')
                    + (('<div style="display:flex;gap:16px;margin-top:10px;flex-wrap:wrap;font-size:13px;">'
                        + ('<span style="color:' + ('#2ecc71' if 'LONG' in ud_pos else '#e74c3c' if 'SHORT' in ud_pos else '#888') + ';font-weight:700;">\U0001f4ca ' + ud_pos + '</span>' if ud_pos else '')
                        + ('<span style="color:#aaa;">\u23f1 ' + ud_hold + '</span>' if ud_hold else '')
                        + ('<span style="color:#aaa;">\U0001f441 ' + ud_chk + '</span>' if ud_chk else '')
                        + '</div>') if (ud_pos or ud_hold or ud_chk) else '')
                    + f'<div style="font-size:11px;color:#555;margin-top:8px;">'
                    f'Entdeckt: {ud.get("discovered_at", "")[:16]} · Quelle: {ud.get("source", "")}'
                    f'</div>'
                    f'</div>',
                    unsafe_allow_html=True
                )
        else:
            st.info("Noch keine Underdogs entdeckt. Starte einen Scan mit dem Button oben rechts.")

    # ── TAB 6: NEWS FEED ──
    with tab6:
        st.markdown('<div class="section-label">📋 Activity Log</div>', unsafe_allow_html=True)
        logs = stock_logs(30)
        if logs:
            for log in logs[:20]:
                level = log.get("level", "INFO")
                icon = {"INFO": "ℹ️", "WARN": "⚠️", "ERROR": "❌", "DEBUG": "🔍"}.get(level, "📌")
                st.markdown(
                    f'<div style="font-size:12px;color:#888;padding:4px 0;">'
                    f'{icon} <b>[{log.get("agent", "?")}]</b> {log.get("message", "")} '
                    f'<span style="color:#555;">{log.get("created_at", "")[:19]}</span></div>',
                    unsafe_allow_html=True
                )
        else:
            st.info("Noch keine Aktivität.")

    # ── TAB 7: SETTINGS ──
    with tab7:
        st.markdown('<div class="section-label">⚙️ Settings</div>', unsafe_allow_html=True)
        settings = stock_load_settings()

        # Watchlist management
        st.markdown("**📈 Watchlist**")
        watchlist = get_watchlist()
        if watchlist:
            wl_tickers = [w["ticker"] for w in watchlist]
            st.markdown(f"Aktuell: **{', '.join(wl_tickers)}**")

            remove = st.selectbox("Ticker entfernen:", ["---"] + wl_tickers, key="remove_ticker")
            if remove != "---" and st.button("❌ Entfernen", key="do_remove"):
                remove_ticker(remove)
                st.rerun()

        new_ticker = st.text_input("Ticker hinzufügen:", placeholder="z.B. GOOGL", key="add_ticker_input")
        if st.button("➕ Hinzufügen", key="do_add"):
            if new_ticker.strip():
                add_ticker(new_ticker.strip().upper())
                st.success(f"{new_ticker.upper()} hinzugefügt!")
                st.rerun()

        st.markdown("---")

        with st.form("stock_settings_form"):
            st.markdown("**Signal Parameters**")
            sc1, sc2, sc3 = st.columns(3)
            with sc1:
                bull_thresh = st.slider("Bullish Threshold", 0.1, 0.8,
                                       float(settings.get("sentiment_bullish_threshold", 0.3)), 0.05)
            with sc2:
                bear_thresh = st.slider("Bearish Threshold", -0.8, -0.1,
                                       float(settings.get("sentiment_bearish_threshold", -0.3)), 0.05)
            with sc3:
                min_conf = st.slider("Min Confidence (%)", 10, 90,
                                    int(settings.get("signal_confidence_min", 40)))

            scan_int = st.number_input("Scan Interval (seconds)",
                                      value=int(settings.get("scan_interval_seconds", 600)), step=60)

            if st.form_submit_button("💾 Save", use_container_width=True, type="primary"):
                stock_save_settings({
                    "sentiment_bullish_threshold": bull_thresh,
                    "sentiment_bearish_threshold": bear_thresh,
                    "signal_confidence_min": min_conf,
                    "scan_interval_seconds": scan_int,
                    "bot_status": settings.get("bot_status", "PAUSED"),
                    "watchlist": settings.get("watchlist", "AAPL,TSLA,NVDA"),
                })
                st.success("Settings saved!")
                st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
# ROUTER
# ═══════════════════════════════════════════════════════════════════════════════

view = st.session_state.get("bot_view", "landing")

if view == "polymarket":
    render_polymarket_bot()
elif view == "stock":
    render_stock_bot()
else:
    render_landing()

st.markdown("<br><br>", unsafe_allow_html=True)
