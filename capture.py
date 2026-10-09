import os, sys, time, httpx
from dotenv import load_dotenv
load_dotenv()

BASE = "https://api-m.sandbox.paypal.com"
auth = (os.environ["PAYPAL_CLIENT_ID"], os.environ["PAYPAL_CLIENT_SECRET"])

def post(url, retries=6, **kw):
    for attempt in range(retries):
        try:
            with httpx.Client(timeout=20) as client:   # fresh connection each try
                return client.post(url, **kw)
        except httpx.TransportError as e:               # ConnectError, ReadError, timeouts
            wait = min(2 ** attempt, 15)
            print(f"{type(e).__name__}: retrying in {wait}s")
            time.sleep(wait)
    raise SystemExit("Network still failing. Fix the connection first.")

order_id = sys.argv[1]
token = post(f"{BASE}/v1/oauth2/token", auth=auth,
             data={"grant_type": "client_credentials"}).json()["access_token"]

r = post(f"{BASE}/v2/checkout/orders/{order_id}/capture",
         headers={"Authorization": f"Bearer {token}",
                  "Content-Type": "application/json",
                  "PayPal-Request-Id": f"capture-{order_id}"})
print(r.status_code, r.json().get("status"))