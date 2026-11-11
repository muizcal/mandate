import os, sqlite3, sys

if "--wipe" in sys.argv:
    if os.path.exists("mandate.db"):
        os.remove("mandate.db")
    print("mandate.db deleted: fresh history, $0 spent. Restart the server.")
else:
    c = sqlite3.connect("mandate.db")
    n = c.execute("UPDATE sessions SET status='cancelled' "
                  "WHERE status IN ('awaiting_payment','running','awaiting_approval')").rowcount
    c.commit()
    print(f"cancelled {n} stale sessions (frees their reserved budget)")