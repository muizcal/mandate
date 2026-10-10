import json, sqlite3, time
from contextlib import contextmanager
from datetime import datetime
from decimal import Decimal

DB_PATH = "mandate.db"


@contextmanager
def conn():
    c = sqlite3.connect(DB_PATH, timeout=10)
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init():
    with conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS sessions(
            id TEXT PRIMARY KEY, goal TEXT, status TEXT, created_at REAL,
            total TEXT, order_id TEXT, approve_url TEXT,
            approval_summary TEXT, final_text TEXT);
        CREATE TABLE IF NOT EXISTS events(
            id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT, ts REAL,
            event TEXT, data TEXT);
        """)


def create_session(sid: str, goal: str):
    with conn() as c:
        c.execute("INSERT INTO sessions(id, goal, status, created_at) "
                  "VALUES (?,?,?,?)", (sid, goal, "running", time.time()))


def update_session(sid: str, **fields):
    allowed = {"status", "total", "order_id", "approve_url",
               "approval_summary", "final_text"}
    cols = [k for k in fields if k in allowed]
    if not cols:
        return
    sql = "UPDATE sessions SET " + ", ".join(f"{k}=?" for k in cols) + " WHERE id=?"
    vals = [None if fields[k] is None else str(fields[k]) for k in cols]
    with conn() as c:
        c.execute(sql, vals + [sid])


def add_event(sid: str, event: str, data: dict):
    with conn() as c:
        c.execute("INSERT INTO events(session_id, ts, event, data) VALUES (?,?,?,?)",
                  (sid, time.time(), event, json.dumps(data, default=str)))


def get_session(sid: str) -> dict | None:
    with conn() as c:
        r = c.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone()
    return dict(r) if r else None


def find_by_order(order_id: str) -> dict | None:
    with conn() as c:
        r = c.execute("SELECT * FROM sessions WHERE order_id=?", (order_id,)).fetchone()
    return dict(r) if r else None


def list_sessions(limit: int = 100) -> list[dict]:
    with conn() as c:
        rows = c.execute("SELECT * FROM sessions ORDER BY created_at DESC LIMIT ?",
                         (limit,)).fetchall()
    return [dict(r) for r in rows]


def _parse(r) -> dict:
    d = dict(r)
    d["data"] = json.loads(d["data"])
    return d


def session_events(sid: str) -> list[dict]:
    with conn() as c:
        rows = c.execute("SELECT id, ts, event, data FROM events "
                         "WHERE session_id=? ORDER BY id", (sid,)).fetchall()
    return [_parse(r) for r in rows]


def recent_events(limit: int = 300) -> list[dict]:
    with conn() as c:
        rows = c.execute(
            "SELECT e.id, e.session_id, e.ts, e.event, e.data, s.goal "
            "FROM events e LEFT JOIN sessions s ON s.id = e.session_id "
            "ORDER BY e.id DESC LIMIT ?", (limit,)).fetchall()
    return [_parse(r) for r in rows]


def spent_this_month() -> Decimal:
    start = datetime.now().replace(day=1, hour=0, minute=0,
                                   second=0, microsecond=0).timestamp()
    with conn() as c:
        rows = c.execute(
            "SELECT total FROM sessions WHERE created_at>=? "
            "AND status IN ('paid','awaiting_payment')", (start,)).fetchall()
    return sum((Decimal(r["total"]) for r in rows if r["total"]), Decimal("0"))


init()