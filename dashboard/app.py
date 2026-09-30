"""Dashboard 6 panel cho Day 13, đọc từ data/logs.jsonl theo contract config/dashboard.yaml.

Chạy (venv riêng, không cài chung với API):
    .venv-dashboard/Scripts/streamlit run dashboard/app.py      # Windows
    .venv-dashboard/bin/streamlit run dashboard/app.py          # macOS/Linux
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT = yaml.safe_load((REPO_ROOT / "config" / "dashboard.yaml").read_text(encoding="utf-8"))["dashboard"]
PANELS = {panel["id"]: panel for panel in CONTRACT["panels"]}
TIME_RANGE = timedelta(minutes=CONTRACT["time_range_minutes"])
REFRESH_SECONDS = CONTRACT["refresh_seconds"]
LOG_PATH = REPO_ROOT / PANELS["latency"]["source"]
THRESHOLD_COLOR = "#d62728"

st.set_page_config(page_title=CONTRACT["title"], layout="wide")


def load_logs() -> pd.DataFrame:
    if not LOG_PATH.exists():
        return pd.DataFrame()
    records = []
    for line in LOG_PATH.read_text(encoding="utf-8").splitlines():
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    df = pd.DataFrame(records)
    if df.empty or "ts" not in df:
        return pd.DataFrame()
    df["ts"] = pd.to_datetime(df["ts"], utc=True)  # log ghi giờ UTC
    df["minute"] = df["ts"].dt.floor("1min")
    return df


def threshold_label(panel_id: str) -> str:
    t = PANELS[panel_id]["threshold"]
    op = "≤" if t["operator"] == "lte" else "≥"
    return f"threshold: {t['aggregation']} {op} {t['value']} {PANELS[panel_id]['unit']}"


def add_threshold(fig: go.Figure, panel_id: str) -> go.Figure:
    t = PANELS[panel_id]["threshold"]
    fig.add_hline(
        y=t["value"],
        line_dash="dash",
        line_color=THRESHOLD_COLOR,
        annotation_text=threshold_label(panel_id),
        annotation_position="top left",
    )
    return fig


def style(fig: go.Figure, panel_id: str, x_range: tuple[datetime, datetime] | None) -> go.Figure:
    fig.update_layout(
        height=320,
        margin=dict(l=10, r=10, t=30, b=10),
        yaxis_title=PANELS[panel_id]["unit"],
        xaxis_title="time (UTC)" if x_range else None,
        legend=dict(orientation="h", y=-0.25),
    )
    if x_range:
        fig.update_xaxes(range=list(x_range))
    return fig


def panel_header(panel_id: str) -> None:
    panel = PANELS[panel_id]
    st.subheader(panel["title"])
    st.caption(f"unit: `{panel['unit']}` · {threshold_label(panel_id)} · events: {', '.join(panel['events'])}")


def status(value: float, panel_id: str) -> str:
    t = PANELS[panel_id]["threshold"]
    ok = value <= t["value"] if t["operator"] == "lte" else value >= t["value"]
    return "OK" if ok else "BREACH"


def render(df_all: pd.DataFrame, anchor_to_last_log: bool) -> None:
    if df_all.empty:
        st.warning(f"Chưa có log trong {LOG_PATH}. Chạy API + scripts/load_test.py trước.")
        return

    end = df_all["ts"].max() if anchor_to_last_log else pd.Timestamp(datetime.now(timezone.utc))
    start = end - TIME_RANGE
    x_range = (start, end)
    df = df_all[(df_all["ts"] > start) & (df_all["ts"] <= end)]
    st.caption(
        f"Time range: {CONTRACT['time_range_minutes']} phút · {start:%Y-%m-%d %H:%M} → {end:%H:%M} UTC · "
        f"auto refresh {REFRESH_SECONDS}s · nguồn `{LOG_PATH.relative_to(REPO_ROOT)}` · {len(df)} records"
    )

    events = df["event"] if "event" in df else pd.Series(dtype=str)
    received = df[events == "request_received"]
    sent = df[events == "response_sent"]
    failed = df[events == "request_failed"]

    col1, col2 = st.columns(2)

    # 1. Latency
    with col1:
        panel_header("latency")
        if sent.empty:
            st.info("Không có response_sent trong cửa sổ.")
        else:
            by_min = sent.groupby("minute").agg(
                p50=("latency_ms", lambda s: s.quantile(0.50)),
                p95=("latency_ms", lambda s: s.quantile(0.95)),
                p99=("latency_ms", lambda s: s.quantile(0.99)),
                ttft_p95=("ttft_ms", lambda s: s.quantile(0.95)),
            ).reset_index()
            m1, m2, m3, m4 = st.columns(4)
            p95 = sent["latency_ms"].quantile(0.95)
            m1.metric("P50", f"{sent['latency_ms'].quantile(0.50):.0f} ms")
            m2.metric("P95", f"{p95:.0f} ms", status(p95, "latency"), delta_color="off")
            m3.metric("P99", f"{sent['latency_ms'].quantile(0.99):.0f} ms")
            m4.metric("TTFT P95", f"{sent['ttft_ms'].quantile(0.95):.0f} ms")
            fig = px.line(by_min, x="minute", y=["p50", "p95", "p99", "ttft_p95"], markers=True)
            st.plotly_chart(style(add_threshold(fig, "latency"), "latency", x_range), width="stretch")

    # 2. Traffic
    with col2:
        panel_header("traffic")
        per_min = received.groupby("minute").size().rename("requests").reset_index()
        m1, m2 = st.columns(2)
        m1.metric("Total requests", len(received))
        rate = per_min["requests"].mean() if not per_min.empty else 0.0
        m2.metric("Avg rate (active minutes)", f"{rate:.1f} req/min", status(rate, "traffic"), delta_color="off")
        fig = px.bar(per_min, x="minute", y="requests")
        st.plotly_chart(style(add_threshold(fig, "traffic"), "traffic", x_range), width="stretch")

    col3, col4 = st.columns(2)

    # 3. Errors + retrieval success
    with col3:
        panel_header("errors")
        error_rate = len(failed) / len(received) * 100 if len(received) else 0.0
        # Retrieval success tính trên mọi event có tool_success (response_sent + request_failed)
        tool = df[df["tool_success"].notna()] if "tool_success" in df else pd.DataFrame()
        tool_rate = (tool["tool_success"] == True).mean() * 100 if not tool.empty else 0.0  # noqa: E712
        m1, m2, m3 = st.columns(3)
        m1.metric("Error rate", f"{error_rate:.1f} %", status(error_rate, "errors"), delta_color="off")
        m2.metric("Retrieval success", f"{tool_rate:.1f} %")
        m3.metric("Failed requests", len(failed))
        recv_min = received.groupby("minute").size()
        fail_min = failed.groupby("minute").size().reindex(recv_min.index, fill_value=0)
        err_df = (fail_min / recv_min * 100).rename("error_rate_pct").reset_index()
        fig = px.line(err_df, x="minute", y="error_rate_pct", markers=True)
        st.plotly_chart(style(add_threshold(fig, "errors"), "errors", x_range), width="stretch")
        if not failed.empty and "error_type" in failed:
            st.caption("Breakdown theo error_type: " + ", ".join(
                f"`{k}`={v}" for k, v in failed["error_type"].value_counts().items()
            ))

    # 4. Cost
    with col4:
        panel_header("cost")
        cost_min = sent.groupby("minute")["cost_usd"].sum().rename("cost_per_minute").reset_index()
        cost_min["cumulative_total"] = cost_min["cost_per_minute"].cumsum()
        total = sent["cost_usd"].sum() if not sent.empty else 0.0
        m1, m2 = st.columns(2)
        m1.metric("Total (window)", f"${total:.4f}", status(total, "cost"), delta_color="off")
        m2.metric("Avg / request", f"${(sent['cost_usd'].mean() if not sent.empty else 0):.5f}")
        fig = go.Figure()
        fig.add_bar(x=cost_min["minute"], y=cost_min["cost_per_minute"], name="sum by minute")
        fig.add_scatter(x=cost_min["minute"], y=cost_min["cumulative_total"], name="cumulative total", mode="lines+markers")
        st.plotly_chart(style(add_threshold(fig, "cost"), "cost", x_range), width="stretch")

    col5, col6 = st.columns(2)

    # 5. Tokens
    with col5:
        panel_header("tokens")
        tok = pd.DataFrame({
            "field": ["tokens_in", "tokens_out"],
            "tokens": [sent["tokens_in"].sum() if not sent.empty else 0, sent["tokens_out"].sum() if not sent.empty else 0],
        })
        m1, m2 = st.columns(2)
        m1.metric("tokens_in (sum)", f"{int(tok.tokens[0]):,}", status(tok.tokens[0], "tokens"), delta_color="off")
        m2.metric("tokens_out (sum)", f"{int(tok.tokens[1]):,}", status(tok.tokens[1], "tokens"), delta_color="off")
        fig = px.bar(tok, x="field", y="tokens", color="field", text_auto=True)
        st.plotly_chart(style(add_threshold(fig, "tokens"), "tokens", None), width="stretch")

    # 6. Quality
    with col6:
        panel_header("quality")
        q_min = sent.groupby("minute")["quality_score"].mean().rename("mean_quality").reset_index()
        q_mean = sent["quality_score"].mean() if not sent.empty else 0.0
        st.metric("Mean quality", f"{q_mean:.3f}", status(q_mean, "quality"), delta_color="off")
        fig = px.line(q_min, x="minute", y="mean_quality", markers=True)
        fig.update_yaxes(range=[0, 1.05])
        st.plotly_chart(style(add_threshold(fig, "quality"), "quality", x_range), width="stretch")


st.title(CONTRACT["title"])
anchor = st.sidebar.toggle(
    "Neo cửa sổ vào log cuối cùng",
    value=False,
    help="Mặc định cửa sổ 60 phút kết thúc ở thời điểm hiện tại. Bật để xem lại log cũ.",
)


@st.fragment(run_every=REFRESH_SECONDS)
def live() -> None:
    render(load_logs(), anchor)


live()
