import os, socket, time

import httpx
from dotenv import load_dotenv

load_dotenv()
all_ok = True


def check(name, fn):
    global all_ok
    t = time.time()
    try:
        detail = fn()
        print(f"PASS  {name:26s} {time.time() - t:4.1f}s  {detail or ''}")
    except Exception as e:
        all_ok = False
        print(f"FAIL  {name:26s} {time.time() - t:4.1f}s  {type(e).__name__}: {str(e)[:140]}")


def env():
    need = ["PAYPAL_CLIENT_ID", "PAYPAL_CLIENT_SECRET", "CHANNEL3_API_KEY",
            "GEMINI_API_KEY", "GEMINI_MODEL"]
    missing = [k for k in need if not os.getenv(k)]
    if missing:
        raise RuntimeError("missing in .env: " + ", ".join(missing))
    return "model=" + os.environ["GEMINI_MODEL"]


def dns(host):
    return lambda: socket.getaddrinfo(host, 443)[0][4][0]


def paypal():
    r = httpx.post("https://api-m.sandbox.paypal.com/v1/oauth2/token",
                   auth=(os.environ["PAYPAL_CLIENT_ID"], os.environ["PAYPAL_CLIENT_SECRET"]),
                   data={"grant_type": "client_credentials"}, timeout=15)
    r.raise_for_status()
    return "token ok"


def channel3():
    r = httpx.post("https://api.trychannel3.com/v1/search",
                   headers={"x-api-key": os.environ["CHANNEL3_API_KEY"]},
                   json={"query": "stapler", "limit": 1}, timeout=20)
    r.raise_for_status()
    return f"{len(r.json().get('products', []))} product(s)"


def gemini():
    from google import genai
    from google.genai import types
    c = genai.Client(http_options=types.HttpOptions(timeout=30_000))
    r = c.models.generate_content(model=os.environ["GEMINI_MODEL"],
                                  contents="Reply with the single word OK.")
    return "replied: " + (r.text or "").strip()[:20]


check("env vars", env)
for h in ["generativelanguage.googleapis.com", "api.trychannel3.com",
          "api-m.sandbox.paypal.com"]:
    check("DNS " + h.split(".")[0], dns(h))
check("PayPal sandbox auth", paypal)
check("Channel3 search", channel3)
check("Gemini model call", gemini)

print("\nGOOD TO GO" if all_ok else "\nNOT READY: fix the FAIL lines above first")