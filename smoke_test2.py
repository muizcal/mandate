import os, uuid, httpx
from dotenv import load_dotenv
load_dotenv()

BASE = "https://api-m.sandbox.paypal.com"
auth = (os.environ["PAYPAL_CLIENT_ID"], os.environ["PAYPAL_CLIENT_SECRET"])

token = httpx.post(f"{BASE}/v1/oauth2/token", auth=auth,
                   data={"grant_type": "client_credentials"}).json()["access_token"]
headers = {"Authorization": f"Bearer {token}",
           "PayPal-Request-Id": str(uuid.uuid4())}  # idempotency key

order = httpx.post(f"{BASE}/v2/checkout/orders", headers=headers, json={
    "intent": "CAPTURE",
    "purchase_units": [{"amount": {"currency_code": "USD", "value": "12.50"}}],
    "payment_source": {"paypal": {"experience_context": {
        "return_url": "https://example.com/return",
        "cancel_url": "https://example.com/cancel",
        "user_action": "PAY_NOW"}}},
}).json()

print(order["id"], order["status"])
for link in order["links"]:
    print(link["rel"], link["href"])
    if link["rel"] in ("payer-action", "approve"):
        approve_url = link["href"]

print("\nOpen this, log in with your PERSONAL sandbox account, approve:")
print(approve_url)
input("\nAfter approving (you'll land on example.com), press Enter to capture...")

cap = httpx.post(f"{BASE}/v2/checkout/orders/{order['id']}/capture",
                 headers={**headers, "PayPal-Request-Id": str(uuid.uuid4()),
                          "Content-Type": "application/json"}).json()
print(cap.get("status"), cap.get("id"))