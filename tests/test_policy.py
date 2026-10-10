from decimal import Decimal as D
from app.policy import Policy, CartItem, Decision, evaluate

P = Policy()


def item(price="20", qty=1, cat="office supplies", merchant="Acme", path=None):
    return CartItem(name="x", category=cat, category_path=path or [],
                    merchant=merchant, unit_price=D(price), quantity=qty)


def test_small_cart_allowed():
    assert evaluate(P, [item("20", 2)]).decision == Decision.ALLOW

def test_over_threshold_needs_approval():
    assert evaluate(P, [item("60", 2)]).decision == Decision.NEEDS_APPROVAL

def test_over_order_limit_denied():
    assert evaluate(P, [item("200", 2)]).decision == Decision.DENY

def test_bad_category_denied():
    assert evaluate(P, [item(cat="electronics")]).decision == Decision.DENY

def test_monthly_budget_denied():
    r = evaluate(P, [item("50")], spent_this_month=D("980"))
    assert r.decision == Decision.DENY

def test_blocked_merchant_denied():
    p = Policy(blocked_merchants={"Shady"})
    assert evaluate(p, [item(merchant="Shady")]).decision == Decision.DENY

def test_deny_beats_approval():
    # above threshold AND bad category: must be DENY, not NEEDS_APPROVAL
    assert evaluate(P, [item("150", cat="electronics")]).decision == Decision.DENY

def test_leaf_category_allowed_without_allowing_top_level():
    batteries = item("10", 2, cat="electronics > batteries",
                     path=["electronics", "electronics accessories", "power", "batteries"])
    assert evaluate(P, [batteries]).decision == Decision.ALLOW

def test_sibling_category_under_same_top_level_denied():
    laptop = item("250", cat="electronics > laptops",
                  path=["electronics", "computers", "laptops"])
    assert evaluate(P, [laptop]).decision == Decision.DENY