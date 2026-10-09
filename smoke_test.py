import os, httpx
from dotenv import load_dotenv
load_dotenv()

BASE = "https://api-m.sandbox.paypal.com"
auth = (os.environ["PAYPAL_CLIENT_ID"], os.environ["PAYPAL_CLIENT_SECRET"])

token = httpx.post(f"{BASE}/v1/oauth2/token", auth=auth,
                   data={"grant_type": "client_credentials"}).json()["access_token"]

order = httpx.post(f"{BASE}/v2/checkout/orders",
    headers={"Authorization": f"Bearer {token}"},
    json={"intent": "CAPTURE",
          "purchase_units": [{"amount": {"currency_code": "USD", "value": "12.50"}}]}
).json()

print(order["id"], order["status"])  # expect CREATED
for link in order["links"]:
    if link["rel"] == "payer-action":
        print("Approve here:", link["href"])