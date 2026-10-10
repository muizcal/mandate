import hashlib, os, time, uuid
from decimal import Decimal

from dotenv import load_dotenv
from google import genai
from google.genai import errors, types

from app import db
from app.catalog import search_products, to_cart_item
from app.paypal_client import PayPalClient
from app.policy import Decision, Policy, evaluate

load_dotenv()
MODEL = os.environ["GEMINI_MODEL"]
MAX_STEPS = 12
client = genai.Client()

DECLS = [
    types.FunctionDeclaration(
        name="search_products",
        description="Search the product catalog. Returns in-stock products with "
                    "their cheapest price. Call once per item the owner wants.",
        parameters=types.Schema(type="OBJECT", properties={
            "query": types.Schema(type="STRING",
                                  description="Specific product search text")},
            required=["query"])),
    types.FunctionDeclaration(
        name="propose_cart",
        description="Propose a cart using ONLY product_ids returned by "
                    "search_products. The policy engine checks it and returns "
                    "allow, needs_approval or deny, with reasons.",
        parameters=types.Schema(type="OBJECT", properties={
            "items": types.Schema(type="ARRAY", items=types.Schema(
                type="OBJECT", properties={
                    "product_id": types.Schema(type="STRING"),
                    "quantity": types.Schema(type="INTEGER")},
                required=["product_id", "quantity"]))},
            required=["items"])),
    types.FunctionDeclaration(
        name="submit_for_payment",
        description="Submit the most recently proposed cart for payment. "
                    "Takes no arguments. Only succeeds if policy allows it or "
                    "the owner approves."),
]


def system_prompt(p: Policy) -> str:
    return f"""You are Mandate, a purchasing agent for a small business owner.

Process:
1. For each item the owner wants, call search_products with a specific query.
2. Pick relevant products only. Results are noisy: ignore wrong items,
   novelty/seasonal products, and bulk or pallet listings far above a normal
   price. Prefer the cheapest relevant option.
3. Call propose_cart with product_ids from the search results and quantities.
   Never invent ids or prices.
4. If the decision is "deny", read the reasons. If you can fix it (smaller
   quantity, cheaper item) re-propose, at most twice. Otherwise explain to the
   owner and stop.
5. If "allow" or "needs_approval", call submit_for_payment. For needs_approval
   the owner is asked inside that tool.
6. Report honestly using only tool results. Never say a purchase happened
   unless submit_for_payment returned status "order_created".

The owner's limits (enforced by code, not by you): per-order limit
${p.per_order_limit}, approval needed above ${p.approval_threshold}, allowed
categories: {sorted(p.allowed_categories)}."""


class Session:
    def __init__(self, policy: Policy, spent_this_month=Decimal("0"),
                 ask_owner=None, paypal=None):
        self.id = uuid.uuid4().hex[:8]
        self.policy, self.spent = policy, spent_this_month
        self.ask_owner = ask_owner or (lambda summary: False)
        self.paypal = paypal or PayPalClient()
        self.catalog, self.cart, self.result, self.order = {}, None, None, None

    def log(self, event: str, **data):
        db.add_event(self.id, event, data)

    def describe(self) -> str:
        lines = [f"{i.quantity} x {i.name[:60]} ({i.merchant}) @ ${i.unit_price}"
                 for i in self.cart]
        return "\n".join(lines) + f"\nTOTAL ${self.result.total}"

    # ---- tools -------------------------------------------------------
    def t_search_products(self, query: str):
        try:
            results = search_products(query, limit=6)
        except Exception as e:
            self.log("search_error", query=query, error=str(e))
            return {"error": "search failed, try a different query"}
        for r in results:
            self.catalog[r["product_id"]] = r
        self.log("search", query=query, found=len(results))
        keys = ("product_id", "title", "brand", "merchant", "unit_price", "category")
        return {"products": [{k: r[k] for k in keys} for r in results]}

    def t_propose_cart(self, items: list):
        cart = []
        for it in items:
            r = self.catalog.get(it.get("product_id"))
            if r is None:
                return {"error": f"unknown product_id {it.get('product_id')}; "
                                 "use ids from search_products"}
            cart.append(to_cart_item(r, int(it["quantity"])))
        result = evaluate(self.policy, cart, self.spent)
        self.cart, self.result = cart, result
        self.log("propose_cart", decision=result.decision.value,
                 total=str(result.total), reasons=result.reasons,
                 items=[(i.name, i.merchant, str(i.unit_price), i.quantity)
                        for i in cart])
        return {"decision": result.decision.value, "total": str(result.total),
                "reasons": result.reasons}

    def t_submit_for_payment(self):
        if self.result is None:
            return {"error": "No cart proposed yet. Call propose_cart first."}
        if self.order:
            return {"error": "Cart already submitted."}
        decision = self.result.decision
        if decision == Decision.DENY:
            self.log("submit_blocked", reasons=self.result.reasons)
            return {"status": "refused", "reasons": self.result.reasons}
        if decision == Decision.NEEDS_APPROVAL:
            approved = bool(self.ask_owner(self.describe()))
            self.log("owner_decision", approved=approved)
            if not approved:
                return {"status": "owner_declined"}
        key = hashlib.sha256((self.id + self.describe()).encode()).hexdigest()[:24]
        self.order = self.paypal.create_order(
            self.result.total, self.describe().replace("\n", "; "), key)
        self.log("order_created", order_id=self.order["id"],
                 total=str(self.result.total),
                 approve_url=self.order["approve_url"])
        return {"status": "order_created", "order_id": self.order["id"],
                "total": str(self.result.total),
                "note": "Buyer still has to approve the payment in PayPal."}

    def dispatch(self, name: str, args: dict):
        fn = {"search_products": self.t_search_products,
              "propose_cart": self.t_propose_cart,
              "submit_for_payment": self.t_submit_for_payment}.get(name)
        if fn is None:
            return {"error": f"unknown tool {name}"}
        try:
            return fn(**args)
        except Exception as e:
            self.log("tool_error", tool=name, error=repr(e))
            return {"error": f"{name} failed: {e}"}


def _generate(contents, config, retries=5):
    for attempt in range(retries):
        try:
            return client.models.generate_content(
                model=MODEL, contents=contents, config=config)
        except errors.APIError as e:
            if e.code in (429, 500, 503) and attempt < retries - 1:
                time.sleep(min(2 ** attempt * 2, 30))
                continue
            raise


def run_agent(goal: str, session: Session) -> str:
    config = types.GenerateContentConfig(
        system_instruction=system_prompt(session.policy),
        tools=[types.Tool(function_declarations=DECLS)],
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )
    contents = [types.Content(role="user", parts=[types.Part(text=goal)])]
    session.log("goal", goal=goal)

    for _ in range(MAX_STEPS):
        resp = _generate(contents, config)
        if not resp.candidates or not resp.candidates[0].content:
            return "The model returned no content."
        contents.append(resp.candidates[0].content)   # echo back unchanged
        calls = resp.function_calls or []
        if not calls:
            session.log("final", text=resp.text)
            return resp.text or ""
        parts = []
        for fc in calls:
            out = session.dispatch(fc.name, dict(fc.args or {}))
            parts.append(types.Part.from_function_response(
                name=fc.name, response=out))
        contents.append(types.Content(role="user", parts=parts))

    session.log("max_steps_reached")
    return "Stopped: too many steps without finishing."