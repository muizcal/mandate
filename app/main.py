import threading

from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from app import db
from app.agent import Session, run_agent
from app.paypal_client import PayPalClient
from app.policy import Decision, Policy

app = FastAPI(title="Mandate")

POLICY = Policy()
PAYPAL = PayPalClient()
PENDING: dict[str, dict] = {}     # session_id -> {"event": Event, "approved": bool|None}
APPROVAL_TIMEOUT = 600            # seconds the agent waits for the owner


class GoalBody(BaseModel):
    goal: str = Field(min_length=3, max_length=500)


class DecisionBody(BaseModel):
    approve: bool


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


@app.post("/api/goals")
def submit_goal(body: GoalBody):
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
    return RedirectResponse(f"/api/sessions/{s['id']}")


@app.get("/paypal/cancel")
def paypal_cancel(token: str = ""):
    s = db.find_by_order(token)
    if s:
        db.add_event(s["id"], "buyer_cancelled", {})
        db.update_session(s["id"], status="cancelled")
    return {"status": "cancelled"}