from app.catalog import search_products
for r in search_products("printer paper 8.5x11 case", limit=5):
    print(r["title"][:50], "|", r["merchant"], "|", r["unit_price"], "|", r["category"])