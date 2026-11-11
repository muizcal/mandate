import sqlite3

c = sqlite3.connect("mandate.db")
n = c.execute("UPDATE sessions SET status='error', final_text='Interrupted' "
              "WHERE status IN ('running','awaiting_approval')").rowcount
c.commit()
print("cleaned", n)