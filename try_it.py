from decimal import Decimal
from app.paypal_client import PayPalClient
o = PayPalClient().create_order(Decimal("45.00"), "Mandate test", "demo-001")
print(o)