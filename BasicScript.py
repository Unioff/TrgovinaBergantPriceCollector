import json
import os
import re
import sys

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

ITEMS = [
    {
        "name": "Barcaffe 100g",
        "mercator": "https://mercatoronline.si/izdelek/28867/mleta-kava-classic-barcaffe-100-g",
        "spar": "https://online.spar.si/p/mleta-kava-classic-barcaffe-100g-41060",
        "hitrinakup": "https://hitrinakup.com/izdelki/24",
    },
    {
        "name": "Zlate Jusne Kroglice 90g",
        "mercator": "https://mercatoronline.si/izdelek/31419/zlate-kroglice-zito-90-g",
        "spar": "https://online.spar.si/p/zlate-kroglice-intes-90g-41211",
        "hitrinakup": "https://hitrinakup.com/izdelki/17688",
    },
]
HITRINAKUP_USER = "perc.jeraj@gmail.com"
HITRINAKUP_PASS = "V.9V-P!MeE5yVht"
HEADERS = {"User-Agent": "Mozilla/5.0"}


def get_soup(url: str) -> BeautifulSoup:
    response = requests.get(url, headers=HEADERS, timeout=15)
    response.raise_for_status()
    return BeautifulSoup(response.text, "html.parser")


def get_mercator_price(url: str) -> str | None:
    soup = get_soup(url)

    # Prva cena na strani pripada glavnemu izdelku, priporočeni izdelki sledijo.
    tag = soup.select_one(".price-box .price")
    if tag is None:
        return None

    match = re.search(r"\d+,\d+", tag.get_text())
    return match.group(0).replace(",", ".") if match else None


def get_spar_price(url: str) -> str | None:
    soup = get_soup(url)

    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except json.JSONDecodeError:
            continue
        for item in data if isinstance(data, list) else [data]:
            offers = item.get("offers") if isinstance(item, dict) else None
            if isinstance(offers, dict):
                price = offers.get("priceSpecification", {}).get("price", offers.get("price"))
                if price is not None:
                    return f"{float(price):.2f}"
    return None


def get_hitrinakup_prices(urls: list[str]) -> list[str | None]:
    # Akcijska cena je vidna le prijavljenim uporabnikom (Tuš račun).
    user = os.environ.get("HITRINAKUP_USER", HITRINAKUP_USER)
    password = os.environ.get("HITRINAKUP_PASS", HITRINAKUP_PASS)
    prices: list[float] = []
    results: list[str | None] = []

    def on_response(response) -> None:
        post_data = response.request.post_data or ""
        if response.url.endswith("/graphql") and "getItemDetails" in post_data:
            try:
                item = response.json()["data"]["getItemDetails"]["item"]
            except (ValueError, KeyError, TypeError):
                return
            price = item.get("discountedPrice") or item.get("price")
            if price is not None:
                prices.append(float(price))

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page()
            if user and password:
                page.goto("https://hitrinakup.com/", wait_until="networkidle", timeout=30000)
                page.get_by_role("button", name="Začni z nakupovanjem").first.click()
                page.fill("input[type=email]", user)
                page.fill("input[type=password]", password)
                page.get_by_role("button", name="PRIJAVA", exact=True).click()
                try:
                    page.wait_for_url(re.compile(r"^https://hitrinakup\.com/"), timeout=30000)
                except PlaywrightError as e:
                    raise RuntimeError("Prijava v Hitri Nakup ni uspela") from e
                page.wait_for_load_state("networkidle")
            page.on("response", on_response)
            for url in urls:
                prices.clear()
                page.goto(url, wait_until="networkidle", timeout=30000)
                results.append(f"{prices[0]:.2f}" if prices else None)
        finally:
            browser.close()

    return results


if __name__ == "__main__":
    try:
        hitrinakup = get_hitrinakup_prices([item["hitrinakup"] for item in ITEMS])
        for item, hn_price in zip(ITEMS, hitrinakup):
            spar = get_spar_price(item["spar"])
            mercator = get_mercator_price(item["mercator"])

            print(item["name"])
            print(f"  Spar: {spar} €" if spar else "  Spar: cena ni najdena")
            print(f"  Mercator: {mercator} €" if mercator else "  Mercator: cena ni najdena")
            print(f"  Hitri Nakup: {hn_price} €" if hn_price else "  Hitri Nakup: cena ni najdena")
    except (requests.RequestException, PlaywrightError, RuntimeError) as e:
        sys.exit(f"Napaka pri nalaganju strani: {e}")
