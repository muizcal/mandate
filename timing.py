import json, sqlite3

c = sqlite3.connect("mandate.db")
c.row_factory = sqlite3.Row

print(f'{"total":>8} {"agent":>8} {"model":>8}  searches  status            goal')
for s in c.execute("SELECT id, goal, status FROM sessions "
                   "ORDER BY created_at DESC LIMIT 12"):
    ev = c.execute("SELECT ts, event, data FROM events WHERE session_id=? "
                   "ORDER BY id", (s["id"],)).fetchall()

    def first(name):
        return next((e for e in ev if e["event"] == name), None)

    start = first("goal")
    end = next((e for e in reversed(ev) if e["event"] in ("final", "error")), None)
    asked, decided = first("approval_requested"), first("owner_decision")
    owner_wait = (decided["ts"] - asked["ts"]) if asked and decided else 0
    total = (end["ts"] - start["ts"]) if start and end else None
    model = sum(json.loads(e["data"]).get("seconds", 0)
                for e in ev if e["event"] == "model_call")
    searches = sum(1 for e in ev if e["event"] == "search")
    if total is None:
        print(f'{"n/a":>8} {"":>8} {"":>8}  {searches:>8}  {s["status"]:17s} {s["goal"][:45]}')
    else:
        print(f"{total:7.1f}s {total - owner_wait:7.1f}s {model:7.1f}s  {searches:>8}  "
              f'{s["status"]:17s} {s["goal"][:45]}')