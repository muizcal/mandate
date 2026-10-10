from decimal import Decimal as D

import pytest

from app import db
from app.agent import MAX_SEARCHES, Session
from app.policy import Policy


class FakePayPal:
    def __init__(self):
        self.orders = []

    def create_order(self, amount, description, request_id):
        self.orders.append((amount, description, request_id))
        return {"id": f"ORDER{len(self.orders)}", "status": "PAYER_ACTION_REQUIRED",
                "approve_url": "https://www.sandbox.paypal.com/checkoutnow?token=X"}


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    db.init()


def product(pid, price, category="office supplies", path=None):
    return {"product_id": pid, "title": f"Item {pid}", "category": category,
            "category_path": path or [category], "merchant": "Acme",
            "unit_price": str(price)}


def make(*products, spent="0", ask=None, policy=None):
    pay = FakePayPal()
    s = Session(policy or Policy(), spent_this_month=D(spent), ask_owner=ask, paypal=pay)
    for p in products:
        s.catalog[p["product_id"]] = p
    return s, pay


def test_allowed_order_uses_code_computed_total():
    s, pay = make(product("a", "20"))
    r = s.t_propose_cart([{"product_id": "a", "quantity": 2}])
    assert r["decision"] == "allow"
    out = s.t_submit_for_payment()
    assert out["status"] == "order_created"
    assert pay.orders[0][0] == D("40")


def test_needs_approval_and_owner_approves():
    asked = []
    s, pay = make(product("a", "60"), ask=lambda summary: asked.append(summary) or True)
    assert s.t_propose_cart([{"product_id": "a", "quantity": 2}])["decision"] == "needs_approval"
    assert s.t_submit_for_payment()["status"] == "order_created"
    assert len(asked) == 1 and len(pay.orders) == 1


def test_needs_approval_and_owner_declines():
    s, pay = make(product("a", "60"), ask=lambda summary: False)
    s.t_propose_cart([{"product_id": "a", "quantity": 2}])
    assert s.t_submit_for_payment()["status"] == "owner_declined"
    assert pay.orders == []


def test_denied_cart_refuses_and_creates_no_order():
    laptop = product("l", "1189", "electronics", ["electronics", "computers", "laptops"])
    s, pay = make(laptop)
    assert s.t_propose_cart([{"product_id": "l", "quantity": 1}])["decision"] == "deny"
    assert s.t_submit_for_payment()["status"] == "refused"
    assert pay.orders == []


def test_submit_before_proposal_is_rejected():
    s, pay = make()
    assert "error" in s.t_submit_for_payment()
    assert pay.orders == []


def test_cannot_submit_twice():
    s, pay = make(product("a", "20"))
    s.t_propose_cart([{"product_id": "a", "quantity": 1}])
    s.t_submit_for_payment()
    assert "error" in s.t_submit_for_payment()
    assert len(pay.orders) == 1


def test_unknown_product_id_rejected():
    s, pay = make(product("a", "20"))
    r = s.t_propose_cart([{"product_id": "made-up", "quantity": 1}])
    assert "error" in r and s.cart is None


def test_model_cannot_override_price():
    s, pay = make(product("a", "19.99"))
    r = s.t_propose_cart([{"product_id": "a", "quantity": 1, "unit_price": "0.01"}])
    assert r["total"] == "19.99"


def test_budget_memory_denies_overspend():
    s, pay = make(product("a", "50"), spent="980")
    r = s.t_propose_cart([{"product_id": "a", "quantity": 1}])
    assert r["decision"] == "deny"
    assert any("monthly budget" in x for x in r["reasons"])


def test_batteries_allowed_but_laptops_denied():
    batt = product("b", "10", "batteries", ["electronics", "power", "batteries"])
    lap = product("l", "250", "laptops", ["electronics", "computers", "laptops"])
    s, _ = make(batt, lap)
    assert s.t_propose_cart([{"product_id": "b", "quantity": 2}])["decision"] == "allow"
    assert s.t_propose_cart([{"product_id": "l", "quantity": 1}])["decision"] == "deny"


def test_bad_quantities_are_handled():
    s, pay = make(product("a", "20"))
    assert "error" in s.dispatch("propose_cart", {"items": [{"product_id": "a", "quantity": "abc"}]})
    assert s.t_propose_cart([{"product_id": "a", "quantity": 0}])["decision"] == "deny"
    assert s.t_propose_cart([{"product_id": "a", "quantity": -1}])["decision"] == "deny"
    assert pay.orders == []


def test_search_limit(monkeypatch):
    monkeypatch.setattr("app.agent.search_products", lambda q, limit=6: [])
    s, _ = make()
    for _ in range(MAX_SEARCHES):
        assert "error" not in s.t_search_products("anything")
    assert "Search limit" in s.t_search_products("one more")["error"]


def test_unknown_tool_is_rejected():
    s, _ = make()
    assert "error" in s.dispatch("wire_money", {})