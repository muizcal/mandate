from app.agent import Session, run_agent
from app.policy import Policy


def ask_owner(summary: str) -> bool:
    print("\n=== OWNER APPROVAL NEEDED ===\n" + summary)
    return input("Approve? (y/n): ").strip().lower() == "y"


if __name__ == "__main__":
    goal = input("What should Mandate buy? ")
    s = Session(Policy(), ask_owner=ask_owner)
    print("\n" + run_agent(goal, s))

    if s.order:
        print("\nPay here (incognito, PERSONAL sandbox account):")
        print(s.order["approve_url"])
        input("After approving in PayPal, press Enter to capture...")
        cap = s.paypal.capture_order(s.order["id"])
        s.log("captured", http=cap["http"], status=cap.get("status"))
        print(cap["http"], cap.get("status"))