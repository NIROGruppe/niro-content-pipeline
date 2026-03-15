"""Reusable Plotly chart components for the trading dashboard."""
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime


CHART_LAYOUT = dict(
    template="plotly_dark",
    paper_bgcolor="#0f0f0f",
    plot_bgcolor="#1a1a1a",
    font=dict(color="#ccc"),
    margin=dict(l=40, r=20, t=40, b=40),
)


def pnl_line_chart(trades: list) -> go.Figure:
    """Cumulative P&L over time."""
    if not trades:
        fig = go.Figure()
        fig.update_layout(**CHART_LAYOUT, title="Cumulative P&L")
        fig.add_annotation(text="Keine Trades vorhanden", xref="paper", yref="paper",
                           x=0.5, y=0.5, showarrow=False, font=dict(size=16, color="#666"))
        return fig

    # Sort by settled date
    sorted_trades = sorted(
        [t for t in trades if t.get("settled_at")],
        key=lambda x: x["settled_at"]
    )

    dates = []
    cumulative = []
    running = 0
    for t in sorted_trades:
        running += t.get("pnl", 0)
        dates.append(t["settled_at"][:10])
        cumulative.append(round(running, 2))

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=dates, y=cumulative,
        mode="lines+markers",
        line=dict(color="#e63946", width=2),
        marker=dict(size=6),
        fill="tozeroy",
        fillcolor="rgba(230,57,70,0.1)",
        name="P&L"
    ))
    fig.update_layout(**CHART_LAYOUT, title="Cumulative P&L ($)")
    fig.add_hline(y=0, line_dash="dash", line_color="#444")
    return fig


def win_loss_bar_chart(trades: list) -> go.Figure:
    """Win/Loss distribution bar chart."""
    wins = sum(1 for t in trades if t.get("pnl", 0) > 0)
    losses = sum(1 for t in trades if t.get("pnl", 0) < 0)
    blocked = sum(1 for t in trades if t.get("status") == "blocked")

    fig = go.Figure(data=[
        go.Bar(
            x=["Wins", "Losses", "Blocked"],
            y=[wins, losses, blocked],
            marker_color=["#2ecc71", "#e74c3c", "#f39c12"],
        )
    ])
    fig.update_layout(**CHART_LAYOUT, title="Trade Outcomes")
    return fig


def confidence_distribution(trades: list) -> go.Figure:
    """Distribution of confidence scores."""
    confidences = [t.get("confidence", 0) for t in trades if t.get("confidence")]
    if not confidences:
        fig = go.Figure()
        fig.update_layout(**CHART_LAYOUT, title="Confidence Distribution")
        return fig

    fig = go.Figure(data=[
        go.Histogram(x=confidences, nbinsx=20, marker_color="#e63946")
    ])
    fig.update_layout(**CHART_LAYOUT, title="Confidence Score Distribution")
    return fig


def edge_vs_pnl_scatter(trades: list) -> go.Figure:
    """Edge vs actual P&L scatter plot."""
    settled = [t for t in trades if t.get("status") == "settled" and t.get("edge")]
    if not settled:
        fig = go.Figure()
        fig.update_layout(**CHART_LAYOUT, title="Edge vs P&L")
        return fig

    edges = [t["edge"] * 100 for t in settled]
    pnls = [t.get("pnl", 0) for t in settled]
    colors = ["#2ecc71" if p > 0 else "#e74c3c" for p in pnls]

    fig = go.Figure(data=[
        go.Scatter(
            x=edges, y=pnls,
            mode="markers",
            marker=dict(size=10, color=colors, line=dict(width=1, color="#333")),
        )
    ])
    fig.update_layout(**CHART_LAYOUT, title="Edge (%) vs P&L ($)",
                      xaxis_title="Edge %", yaxis_title="P&L $")
    fig.add_hline(y=0, line_dash="dash", line_color="#444")
    return fig


def postmortem_category_chart(postmortems: list) -> go.Figure:
    """Loss patterns by category."""
    patterns = {}
    for pm in postmortems:
        pattern = pm.get("pattern_detected", "Unknown")
        patterns[pattern] = patterns.get(pattern, 0) + 1

    if not patterns:
        fig = go.Figure()
        fig.update_layout(**CHART_LAYOUT, title="Loss Patterns")
        return fig

    fig = go.Figure(data=[
        go.Bar(
            x=list(patterns.keys()),
            y=list(patterns.values()),
            marker_color="#e74c3c",
        )
    ])
    fig.update_layout(**CHART_LAYOUT, title="Loss Patterns")
    return fig
