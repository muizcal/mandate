import os
import threading
import time
from collections import deque
from contextlib import asynccontextmanager
from decimal import Decimal
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel, Field

load_dotenv()

from app import db
from app.agent import Session, run_agent
from app.paypal_client import PayPalClient
from app.policy import Decision, Policy


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Sessions that were mid-run when the server stopped can never finish.
    with db.conn() as c:
        c.execute("UPDATE sessions SET status='error', "
                  "final_text='Interrupted by a server restart' "
                  "WHERE status IN ('running','awaiting_approval')")
    yield


app = FastAPI(title="Mandate", lifespan=lifespan)

STATIC = Path(__file__).resolve().parent.parent / "static"
MAX_GOALS_PER_HOUR = int(os.getenv("MAX_GOALS_PER_HOUR", "30"))
MAX_ACTIVE_SESSIONS = int(os.getenv("MAX_ACTIVE_SESSIONS", "2"))
_goal_times: deque = deque()
_goal_lock = threading.Lock()


def build_policy() -> Policy:
    """Defaults live in policy.py; any limit can be overridden from .env."""
    overrides = {}
    for env_name, field in (("MONTHLY_BUDGET", "monthly_budget"),
                            ("PER_ORDER_LIMIT", "per_order_limit"),
                            ("APPROVAL_THRESHOLD", "approval_threshold")):
        value = os.getenv(env_name)
        if value:
            overrides[field] = Decimal(value)
    return Policy(**overrides)


POLICY = build_policy()
PAYPAL = PayPalClient()
PENDING: dict[str, dict] = {}     # session_id -> {"event": Event, "approved": bool|None}
APPROVAL_TIMEOUT = 600            # seconds the agent waits for the owner


class GoalBody(BaseModel):
    goal: str = Field(min_length=3, max_length=500)


class DecisionBody(BaseModel):
    approve: bool


def check_capacity():
    """Protects the shared Gemini quota when the demo is public."""
    now = time.time()
    with _goal_lock:
        while _goal_times and now - _goal_times[0] > 3600:
            _goal_times.popleft()
        if len(_goal_times) >= MAX_GOALS_PER_HOUR:
            raise HTTPException(429, "This demo is rate-limited. Please try again later.")
        active = [s for s in db.list_sessions(50)
                  if s["status"] in ("running", "awaiting_approval")]
        if len(active) >= MAX_ACTIVE_SESSIONS:
            raise HTTPException(429, "Other requests are still running. "
                                     "Please wait for one to finish.")
        _goal_times.append(now)


def make_ask_owner(sid: str):
    """Called from the agent's thread. Blocks until the owner decides via the API."""
    def ask(summary: str) -> bool:
        entry = {"event": threading.Event(), "approved": None}
        PENDING[sid] = entry
        db.update_session(sid, status="awaiting_approval", approval_summary=summary)
        db.add_event(sid, "approval_requested", {"summary": summary})
        if not entry["event"].wait(APPROVAL_TIMEOUT):
            entry["approved"] = False
            db.add_event(sid, "approval_timeout", {})
        db.update_session(sid, status="running")
        return bool(entry["approved"])
    return ask


def _worker(session: Session, goal: str):
    sid = session.id
    try:
        text = run_agent(goal, session)
        if session.order:
            status = "awaiting_payment"
        elif PENDING.get(sid, {}).get("approved") is False:
            status = "declined"
        elif session.result and session.result.decision == Decision.DENY:
            status = "denied"
        else:
            status = "no_purchase"
        db.update_session(
            sid, status=status, final_text=text,
            total=session.result.total if session.order else None,
            order_id=session.order["id"] if session.order else None,
            approve_url=session.order["approve_url"] if session.order else None)
    except Exception as e:
        db.add_event(sid, "error", {"error": repr(e)})
        db.update_session(sid, status="error", final_text=f"Agent error: {e}")


@app.get("/")
def dashboard():
    return FileResponse(STATIC / "index.html")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/summary")
def summary():
    return {"spent": str(db.spent_this_month()),
            "policy": POLICY.model_dump(mode="json")}


@app.post("/api/goals")
def submit_goal(body: GoalBody):
    check_capacity()
    session = Session(POLICY, spent_this_month=db.spent_this_month(), paypal=PAYPAL)
    session.ask_owner = make_ask_owner(session.id)
    db.create_session(session.id, body.goal)
    threading.Thread(target=_worker, args=(session, body.goal), daemon=True).start()
    return {"session_id": session.id}


@app.get("/api/sessions")
def sessions():
    return db.list_sessions()


@app.get("/api/sessions/{sid}")
def session_detail(sid: str):
    s = db.get_session(sid)
    if not s:
        raise HTTPException(404, "Unknown session")
    return {**s, "events": db.session_events(sid)}


@app.get("/api/events")
def events():
    return db.recent_events()


@app.post("/api/sessions/{sid}/decision")
def decide(sid: str, body: DecisionBody):
    entry = PENDING.get(sid)
    if not entry or entry["event"].is_set():
        raise HTTPException(409, "No pending approval for this session")
    entry["approved"] = body.approve
    entry["event"].set()
    return {"ok": True}


@app.get("/paypal/return")
def paypal_return(token: str):
    s = db.find_by_order(token)
    if not s:
        raise HTTPException(404, "Unknown order")
    if s["status"] != "paid":
        cap = PAYPAL.capture_order(token)
        ok = cap.get("status") == "COMPLETED"
        db.add_event(s["id"], "captured",
                     {"http": cap.get("http"), "status": cap.get("status")})
        db.update_session(s["id"], status="paid" if ok else "payment_failed")
    return RedirectResponse("/")


@app.get("/paypal/cancel")
def paypal_cancel(token: str = ""):
    s = db.find_by_order(token)
    if s:
        db.add_event(s["id"], "buyer_cancelled", {})
        db.update_session(s["id"], status="cancelled")
    return RedirectResponse("/")