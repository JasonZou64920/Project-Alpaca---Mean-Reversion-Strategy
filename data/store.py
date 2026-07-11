# sqlite storage - bars, signals, orders, fills, snapshots and the control flags
import json
import os
import sqlite3

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(ROOT, "data", "market.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS bars (
    symbol TEXT, ts TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL,
    PRIMARY KEY (symbol, ts));
CREATE TABLE IF NOT EXISTS signals (
    ts TEXT, symbol TEXT, z REAL, action TEXT, note TEXT);
CREATE TABLE IF NOT EXISTS orders (
    order_id TEXT PRIMARY KEY, ts TEXT, symbol TEXT, side TEXT, qty REAL,
    notional REAL, status TEXT, note TEXT);
CREATE TABLE IF NOT EXISTS fills (
    ts TEXT, order_id TEXT, symbol TEXT, side TEXT, qty REAL, price REAL);
CREATE TABLE IF NOT EXISTS snapshots (
    ts TEXT, equity REAL, cash REAL, gross REAL, positions TEXT);
CREATE TABLE IF NOT EXISTS control (
    key TEXT PRIMARY KEY, value TEXT);
"""


def connect(path=DB_PATH):
    con = sqlite3.connect(path, timeout=10)
    con.execute("PRAGMA journal_mode=WAL")   # UI reads while the loop writes
    con.executescript(SCHEMA)
    return con


def save_bars(con, tidy):
    rows = [(r.symbol, str(r.ts), r.open, r.high, r.low, r.close, r.volume)
            for r in tidy.itertuples()]
    con.executemany("INSERT OR REPLACE INTO bars VALUES (?,?,?,?,?,?,?)", rows)
    con.commit()


def log_signal(con, ts, symbol, z, action, note=""):
    con.execute("INSERT INTO signals VALUES (?,?,?,?,?)",
                (str(ts), symbol, float(z), action, note))
    con.commit()


def log_order(con, order):
    """Insert or update one order row - repeated calls track status changes."""
    con.execute("INSERT OR REPLACE INTO orders VALUES (?,?,?,?,?,?,?,?)",
                (order["order_id"], str(order["ts"]), order["symbol"], order["side"],
                 order["qty"], order["notional"], order["status"], order.get("note", "")))
    con.commit()


def log_fill(con, ts, order_id, symbol, side, qty, price):
    con.execute("INSERT INTO fills VALUES (?,?,?,?,?,?)",
                (str(ts), order_id, symbol, side, qty, price))
    con.commit()


def log_snapshot(con, ts, equity, cash, gross, positions):
    con.execute("INSERT INTO snapshots VALUES (?,?,?,?,?)",
                (str(ts), equity, cash, gross, json.dumps(positions)))
    con.commit()


def set_control(con, key, value):
    con.execute("INSERT OR REPLACE INTO control VALUES (?,?)", (key, str(value)))
    con.commit()


def get_control(con, key, default=""):
    row = con.execute("SELECT value FROM control WHERE key=?", (key,)).fetchone()
    return row[0] if row else default


def recent(con, table, n=50):
    """Last n rows of a table, newest first, as a DataFrame for the UI."""
    return pd.read_sql_query(f"SELECT * FROM {table} ORDER BY ts DESC LIMIT {int(n)}", con)


def snapshots(con, n=2000):
    df = pd.read_sql_query(f"SELECT * FROM snapshots ORDER BY ts DESC LIMIT {int(n)}", con)
    return df.iloc[::-1].reset_index(drop=True)   # oldest first for charting
