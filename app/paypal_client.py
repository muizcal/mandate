import os, time, httpx
from decimal import Decimal
from dotenv import load_dotenv

load_dotenv()
BASE = "https://api-m.sandbox.paypal.com"
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:8000")


class PayPalClient:
    def __init__(self):
        self._auth = (os.environ["PAYPAL_CLIENT_ID"],
                      os.environ["PAYPAL_CLIENT_SECRET"])
        self._token, self._expires = None, 0.0

    def _request(self, method, path, retries=6, **kw):
        for attempt in range(retries):
            try:
                with httpx.Client(timeout=20) as c:   # fresh connection per try
                    r = c.request(method, BASE + path, **kw)
                if r.status_code >= 500:
                    raise httpx.TransportError(f"PayPal {r.status_code}")
                return r
            except httpx.TransportError:
                time.sleep(min(2 ** attempt, 15))
        raise RuntimeError("PayPal unreachable after retries")

    def _headers(self, request_id: str | None = None) -> dict:
        if time.time() >= self._expires:
            r = self._request("POST", "/v1/oauth2/token", auth=self._auth,
                              data={"grant_type": "client_credentials"})
            r.raise_for_status()
            j = r.json()
            self._token = j["access_token"]
            self._expires = time.time() + j["expires_in"] - 60
        h = {"Authorization": f"Bearer {self._token}",
             "Content-Type": "application/json"}
        if request_id:
            h["PayPal-Request-Id"] = request_id
        return h

    def create_order(self, amount: Decimal, description: str, request_id: str) -> dict:
        body = {
            "intent": "CAPTURE",
            "purchase_units": [{
                "description": description[:127],
                "amount": {"currency_code": "USD", "value": f"{amount:.2f}"}}],
            "payment_source": {"paypal": {"experience_context": {
                "return_url": f"{APP_BASE_URL}/paypal/return",
                "cancel_url": f"{APP_BASE_URL}/paypal/cancel",
                "user_action": "PAY_NOW"}}},
        }
        r = self._request("POST", "/v2/checkout/orders",
                          headers=self._headers(f"create-{request_id}"), json=body)
        r.raise_for_status()
        o = r.json()
        approve = next(l["href"] for l in o["links"] if l["rel"] == "payer-action")
        return {"id": o["id"], "status": o["status"], "approve_url": approve}

    def capture_order(self, order_id: str) -> dict:
        r = self._request("POST", f"/v2/checkout/orders/{order_id}/capture",
                          headers=self._headers(f"capture-{order_id}"))
        return {"http": r.status_code, **r.json()}