import requests
from datetime import datetime

URL = "https://deadpool.unified-jennet.instaleap.io/api/v3"

HEADERS = {
    "Content-Type": "application/json",
    "dpl-api-key": "febe3691-edb4-498b-b1a6-d6fe1ddd068e",
    "client-name": "e-commerce Moira Engine SPAR_SLOVENIA",
    "client-version": "0.19.390",
    "apollographql-client-name": "e-commerce Moira Engine client SPAR_SLOVENIA",
    "apollographql-client-version": "0.19.390",
    "origin": "https://online.spar.si",
    "referer": "https://online.spar.si/",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36",
    "accept": "*/*",
}

SKU_LIST = [
    "41060",  # Barcaffe
    "41211",  # Tvoj drugi izdelek
    "30438"   # Nivea
]

QUERY = """
query GetProductsBySKU($getProductsBySKUInput: GetProductsBySKUInput!) {
  getProductsBySKU(getProductsBySKUInput: $getProductsBySKUInput) {
    name
    price
    sku
    ean
    stock
    brand
    slug
  }
}
"""


def get_products_by_sku(skus):
    payload = [{
        "operationName": "GetProductsBySKU",
        "variables": {
            "getProductsBySKUInput": {
                "clientId": "SPAR_SLOVENIA",
                "skus": skus,
                "storeReference": "81701"
            }
        },
        "query": QUERY
    }]

    response = requests.post(
        URL,
        headers=HEADERS,
        json=payload,
        timeout=30
    )

    response.raise_for_status()

    return response.json()[0]["data"]["getProductsBySKU"]


def main():
    products = get_products_by_sku(SKU_LIST)

    print()
    print("=" * 120)
    print(f"SPAR CENE - {datetime.now():%Y-%m-%d %H:%M:%S}")
    print("=" * 120)

    for p in products:
        print()
        print(f"SKU      : {p['sku']}")
        print(f"Naziv    : {p['name']}")
        print(f"Cena     : {p['price']} €")
        print(f"Brand    : {p.get('brand', '')}")
        print(f"Zaloga   : {p.get('stock', '')}")
        print(f"Slug     : {p.get('slug', '')}")

        eans = p.get("ean", [])
        if isinstance(eans, list):
            print(f"EAN      : {', '.join(eans)}")
        else:
            print(f"EAN      : {eans}")

        print("-" * 120)


if __name__ == "__main__":
    main()