import os, json, httpx
from dotenv import load_dotenv
load_dotenv()

r = httpx.post(
    "https://api.trychannel3.com/v1/search",
    headers={"x-api-key": os.environ["CHANNEL3_API_KEY"],
             "Content-Type": "application/json"},
    json={"query": "printer paper 8.5x11 case", "limit": 3},
    timeout=30,
)
print(r.status_code)
data = r.json()
print("top-level keys:", list(data.keys()))

products = data.get("products", [])
print("products returned:", len(products))
if products:
    p = products[0]
    print("product keys:", list(p.keys()))
    print(json.dumps({k: p[k] for k in p if k != "description"}, indent=2)[:2500])