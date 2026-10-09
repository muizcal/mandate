import os, time, httpx
from decimal import Decimal
from dotenv import load_dotenv
from app.policy import CartItem

load_dotenv()
URL = "https://api.trychannel3.com/v1/search"


def _post(body: dict, retries: int = 5) -> dict:
    for attempt in range(retries):
        try:
            with httpx.Client(timeout=30) as c:
                r = c.post(URL, json=body, headers={
                    "x-api-key": os.environ["CHANNEL3_API_KEY"],
                    "Content-Type": "application/json"})
            if r.status_code >= 500:
                raise httpx.TransportError(f"Channel3 {r.status_code}")
            r.raise_for_status()
            return r.json()
        except httpx.TransportError:
            time.sleep(min(2 ** attempt, 10))
    raise RuntimeError("Channel3 unreachable after retries")


def _offer_price(offer: dict) -> Decimal | None:
    p = offer.get("price")
    val = p.get("price") if isinstance(p, dict) else p
    return Decimal(str(val)) if val is not None else None


def search_products(query: str, limit: int = 5) -> list[dict]:
    """Return a trimmed list: one entry per product, using its cheapest offer."""
    data = _post({"query": query, "limit": limit})
    results = []
    for p in data.get("products", []):
        priced = [(o, _offer_price(o)) for o in p.get("offers", [])]
        priced = [(o, pr) for o, pr in priced if pr is not None and pr > 0]
        if not priced:
            continue
        offer, price = min(priced, key=lambda t: t[1])
        cat = p.get("category") or {}
        path = cat.get("path") or []
        results.append({
            "product_id": p["id"],
            "title": p["title"],
            "brand": (p.get("brands") or [{}])[0].get("name"),
            "category": (path[0]["title"] if path else cat.get("title", "")).lower(),
            "merchant": offer.get("domain", "unknown"),
            "unit_price": str(price),          # string: keeps Decimal exact in JSON
            "offer_url": offer.get("url"),
            "other_offers": len(priced) - 1,
        })
    return results


def to_cart_item(result: dict, quantity: int) -> CartItem:
    return CartItem(name=result["title"], category=result["category"],
                    merchant=result["merchant"],
                    unit_price=Decimal(result["unit_price"]), quantity=quantity)