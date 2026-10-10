from decimal import Decimal
from enum import Enum
from pydantic import BaseModel, Field


class Decision(str, Enum):
    ALLOW = "allow"
    NEEDS_APPROVAL = "needs_approval"
    DENY = "deny"


class Policy(BaseModel):
    monthly_budget: Decimal = Decimal("1000")
    per_order_limit: Decimal = Decimal("300")
    approval_threshold: Decimal = Decimal("100")
    # Matched against EVERY level of a product's category path, so "office supplies"
    # allows everything under it, while "batteries" allows batteries without
    # allowing all of Electronics.
    allowed_categories: set[str] = Field(default={
        "office supplies", "household cleaning supplies",
        "household paper products", "batteries"})
    blocked_merchants: set[str] = Field(default_factory=set)


class CartItem(BaseModel):
    name: str
    category: str                                   # display text
    category_path: list[str] = Field(default_factory=list)
    merchant: str
    unit_price: Decimal
    quantity: int = 1


class PolicyResult(BaseModel):
    decision: Decision
    total: Decimal
    reasons: list[str]


def cart_total(items: list[CartItem]) -> Decimal:
    return sum((i.unit_price * i.quantity for i in items), Decimal("0"))


def _segments(item: CartItem) -> set[str]:
    return {s.strip().lower() for s in (item.category_path or [item.category])}


def evaluate(policy: Policy, items: list[CartItem],
             spent_this_month: Decimal = Decimal("0")) -> PolicyResult:
    total = cart_total(items)
    deny: list[str] = []

    if not items:
        deny.append("Cart is empty")
    for i in items:
        if not (_segments(i) & policy.allowed_categories):
            deny.append(f"Category '{i.category}' is not allowed ({i.name})")
        if i.merchant in policy.blocked_merchants:
            deny.append(f"Merchant '{i.merchant}' is blocked")
        if i.unit_price <= 0 or i.quantity <= 0:
            deny.append(f"Invalid price or quantity for {i.name}")
    if total > policy.per_order_limit:
        deny.append(f"Total ${total} exceeds per-order limit ${policy.per_order_limit}")
    if spent_this_month + total > policy.monthly_budget:
        deny.append(f"Would exceed monthly budget ${policy.monthly_budget}")

    if deny:  # deny always beats approval
        return PolicyResult(decision=Decision.DENY, total=total, reasons=deny)
    if total > policy.approval_threshold:
        return PolicyResult(decision=Decision.NEEDS_APPROVAL, total=total,
                            reasons=[f"Total ${total} is above approval threshold ${policy.approval_threshold}"])
    return PolicyResult(decision=Decision.ALLOW, total=total,
                        reasons=["Within all limits"])