from app.catalog import _post

for q in ["bubble mailers", "cardboard shipping boxes 12x12x12",
          "packing tape refill roll", "mailing envelopes", "trash bags"]:
    products = _post({"query": q, "limit": 3}).get("products", [])
    print(f"\n{q}")
    for p in products:
        path = " > ".join(x["title"] for x in (p.get("category") or {}).get("path", []))
        print("  ", p["title"][:45], "|", path)