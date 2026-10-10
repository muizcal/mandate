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


def _usable(offer: dict) -> bool:
    price = offer.get("price") or {}
    value = price.get("price")
    return (offer.get("availability") == "InStock"
            and offer.get("condition", "new") == "new"
            and price.get("currency", "USD") == "USD"
            and value is not None and value > 0)


def search_products(query: str, limit: int = 5) -> list[dict]:
    """Return a trimmed list: one entry per product, using its cheapest offer."""
    data = _post({"query": query, "limit": limit})
    results = []
    for p in data.get("products", []):
        priced = [(o, Decimal(str(o["price"]["price"])))
                  for o in p.get("offers", []) if _usable(o)]
        if not priced:
            continue
        offer, price = min(priced, key=lambda t: t[1])
        cat = p.get("category") or {}
        path = [str(x.get("title", "")).strip().lower()
                for x in (cat.get("path") or []) if x.get("title")]
        if not path and cat.get("title"):
            path = [str(cat["title"]).strip().lower()]
        results.append({
            "product_id": p["id"],
            "title": p["title"],
            "brand": (p.get("brands") or [{}])[0].get("name"),
            "category": " > ".join(path),
            "category_path": path,
            "merchant": offer.get("domain", "unknown"),
            "unit_price": str(price),          # string: keeps Decimal exact in JSON
            "offer_url": offer.get("url"),
            "other_offers": len(priced) - 1,
        })
    return results


def to_cart_item(result: dict, quantity: int) -> CartItem:
    return CartItem(name=result["title"], category=result["category"],
                    category_path=result["category_path"],
                    merchant=result["merchant"],
                    unit_price=Decimal(result["unit_price"]), quantity=quantity)