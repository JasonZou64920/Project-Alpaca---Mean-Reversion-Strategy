# streamlit dashboard - monitors the paper loop and edits its settings
# run with: streamlit run ui/app.py   (from the project root)
import json
import os
import sys
from datetime import datetime, timezone

import altair as alt
import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from data import store

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHARTS = os.path.join(HERE, "charts")

st.set_page_config(page_title="Alpaca Mean Reversion", layout="wide")


def age_seconds(iso):
    try:
        return (datetime.now(timezone.utc) - datetime.fromisoformat(iso)).total_seconds()
    except ValueError:
        return None


def age_label(age):
    if age is None:
        return "never"
    return f"{age:,.0f}s ago" if age < 120 else f"{age / 60:,.0f}m ago"


def equity_chart(df):
    """Line chart that does not force a zero baseline - a $100k account moving
    by $50 would otherwise render as a flat line."""
    line = alt.Chart(df).mark_line(color="#2962ff").encode(
        x=alt.X("ts:T", title=None),
        y=alt.Y("equity:Q", scale=alt.Scale(zero=False), title=None,
                axis=alt.Axis(format="$,.0f")),
    ).properties(height=280)
    st.altair_chart(line, use_container_width=True)


def positions_frame(snapshot_row):
    detail = json.loads(snapshot_row["positions"])
    if not detail:
        return pd.DataFrame()
    df = pd.DataFrame(detail).T
    df.index.name = "symbol"
    df["pnl_pct"] = df["unrealized_pl"] / (df["market_value"].abs() - df["unrealized_pl"])
    return df.reset_index()


# ---------- sidebar: control and settings ----------
cfg = config.load()
con = store.connect()

st.sidebar.header("Control")
runstate = store.get_control(con, "runstate", "stopped")
c1, c2 = st.sidebar.columns(2)
if c1.button("Start", use_container_width=True):
    store.set_control(con, "runstate", "running")
    st.rerun()
if c2.button("Stop", use_container_width=True):
    store.set_control(con, "runstate", "stopped")
    st.rerun()
st.sidebar.caption(f"strategy is {store.get_control(con, 'runstate', 'stopped').upper()} - "
                   "the loop picks this up on its next poll. Stop pauses new entries; "
                   "exits and stop-losses keep managing open positions.")

st.sidebar.header("Universe")
stocks_text = st.sidebar.text_area("stocks", ", ".join(cfg["tickers"]["stocks"]), height=80)
crypto_text = st.sidebar.text_area("crypto", ", ".join(cfg["tickers"]["crypto"]), height=60)

st.sidebar.header("Strategy")
entry_z = st.sidebar.number_input("entry z", 0.5, 5.0, float(cfg["strategy"]["entry_z"]), 0.1)
exit_z = st.sidebar.number_input("exit z", 0.1, 2.0, float(cfg["strategy"]["exit_z"]), 0.1)
vol_target = st.sidebar.number_input("vol target per position", 0.005, 0.20,
                                     float(cfg["strategy"]["vol_target"]), 0.005, format="%.3f")

st.sidebar.header("Risk limits")
max_pos = st.sidebar.number_input("max position (pct of equity)", 0.01, 1.0,
                                  float(cfg["risk"]["max_position_pct"]), 0.01)
max_gross = st.sidebar.number_input("max gross exposure (pct)", 0.1, 2.0,
                                    float(cfg["risk"]["max_gross_pct"]), 0.05)
stop_loss = st.sidebar.number_input("stop loss (pct)", 0.01, 0.25,
                                    float(cfg["risk"]["stop_loss_pct"]), 0.01)

if st.sidebar.button("Save settings", use_container_width=True):
    cfg["tickers"]["stocks"] = [s.strip().upper() for s in stocks_text.replace("\n", ",").split(",") if s.strip()]
    cfg["tickers"]["crypto"] = [s.strip().upper() for s in crypto_text.replace("\n", ",").split(",") if s.strip()]
    cfg["strategy"]["entry_z"] = float(entry_z)
    cfg["strategy"]["exit_z"] = float(exit_z)
    cfg["strategy"]["vol_target"] = float(vol_target)
    cfg["risk"]["max_position_pct"] = float(max_pos)
    cfg["risk"]["max_gross_pct"] = float(max_gross)
    cfg["risk"]["stop_loss_pct"] = float(stop_loss)
    config.save(cfg)
    st.sidebar.success("saved - applies on the loop's next poll")

refresh = st.sidebar.selectbox("refresh every", ["5s", "15s", "60s", "off"], index=1)


# ---------- main dashboard ----------
def dashboard():
    con = store.connect()
    snaps = store.snapshots(con)
    last_update = store.get_control(con, "last_update", "")
    age = age_seconds(last_update) if last_update else None
    poll = cfg["execution"]["poll_seconds"]

    connection = store.get_control(con, "connection", "no data")
    if connection == "ok" and (age is None or age > 3 * poll):
        connection = "stale"

    # status bar
    s1, s2, s3, s4, s5 = st.columns(5)
    s1.metric("Connection", connection)
    s2.metric("Mode", store.get_control(con, "mode", "paper"))
    s3.metric("Stock market", store.get_control(con, "market_open", "unknown"))
    s4.metric("Last data", age_label(age))
    if len(snaps):
        latest = snaps.iloc[-1]
        prev_eq = snaps.iloc[-2]["equity"] if len(snaps) > 1 else latest["equity"]
        s5.metric("Equity", f"${latest['equity']:,.0f}",
                  delta=f"{latest['equity'] - prev_eq:,.2f}")
    else:
        s5.metric("Equity", "-")

    # equity curve on top, tradingview-style: chart first, tables below
    source = st.radio("equity curve", ["paper account", "last backtest"],
                      horizontal=True, label_visibility="collapsed")
    if source == "paper account":
        if len(snaps) > 1:
            eq = snaps[["ts", "equity"]].copy()
            eq["ts"] = pd.to_datetime(eq["ts"], format="mixed")
            equity_chart(eq)
        else:
            st.caption("equity curve appears after a few polling cycles of run_paper.py")
    else:
        bt_path = os.path.join(CHARTS, "backtest_equity.csv")
        if os.path.exists(bt_path):
            bt = pd.read_csv(bt_path, parse_dates=[0])
            bt.columns = ["ts", "equity"]
            equity_chart(bt)
        else:
            st.caption("run backtest.py first to see the backtest curve")

    # positions with per-position and total P&L
    st.subheader("Positions")
    if len(snaps):
        pos = positions_frame(snaps.iloc[-1])
        if len(pos):
            total = pd.DataFrame([{"symbol": "TOTAL",
                                   "market_value": pos["market_value"].sum(),
                                   "unrealized_pl": pos["unrealized_pl"].sum()}])
            st.dataframe(pd.concat([pos, total], ignore_index=True),
                         use_container_width=True, hide_index=True,
                         column_config={
                             "qty": st.column_config.NumberColumn(format="%.6f"),
                             "entry": st.column_config.NumberColumn(format="$%.2f"),
                             "price": st.column_config.NumberColumn(format="$%.2f"),
                             "market_value": st.column_config.NumberColumn(format="$%.2f"),
                             "unrealized_pl": st.column_config.NumberColumn(format="$%.2f"),
                             "pnl_pct": st.column_config.NumberColumn(format="percent"),
                         })
        else:
            st.caption("no open positions")
    else:
        st.caption("no snapshots yet - start run_paper.py")

    # recent signals, orders and fills side by side
    t1, t2, t3 = st.columns(3)
    with t1:
        st.subheader("Recent signals")
        st.dataframe(store.recent(con, "signals", 30), use_container_width=True,
                     hide_index=True, height=320)
    with t2:
        st.subheader("Recent orders")
        st.dataframe(store.recent(con, "orders", 30), use_container_width=True,
                     hide_index=True, height=320)
    with t3:
        st.subheader("Recent fills")
        st.dataframe(store.recent(con, "fills", 30), use_container_width=True,
                     hide_index=True, height=320)


if refresh == "off":
    dashboard()
else:
    st.fragment(dashboard, run_every=refresh)()
