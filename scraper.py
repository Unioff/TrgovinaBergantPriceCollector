import json
import os
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

HITRINAKUP_USER = "perc.jeraj@gmail.com"
HITRINAKUP_PASS = "V.9V-P!MeE5yVht"
HEADERS = {"User-Agent": "Mozilla/5.0"}
DB_PATH = Path(__file__).with_name("prices.db")

QUERY = """
SELECT a.id AS artikel_id, a.name AS artikel, t.ID AS trgovina_id, t.Name AS trgovina,
       t.base_url, u.url
FROM artikel_url u
JOIN artikel a ON a.id = u.artikel_id
JOIN trgovina t ON t.ID = u.trgovina_id
ORDER BY a.id, t.ID
"""


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


# Scraper se izbere glede na gostitelja iz trgovina.base_url; trgovine brez scraperja (npr. TrgovinaBergant) so ročne.
SCRAPERS = {
    "mercatoronline.si": get_mercator_price,
    "online.spar.si": get_spar_price,
}
HITRINAKUP_HOST = "hitrinakup.com"


def host_of(url: str | None) -> str:
    return (urlparse(url or "").hostname or "").removeprefix("www.")


def scrape(rows: list[sqlite3.Row]) -> list[str | None]:
    prices: list[str | None] = [None] * len(rows)

    for i, row in enumerate(rows):
        scraper = SCRAPERS.get(host_of(row["base_url"]))
        if scraper is None:
            continue
        try:
            prices[i] = scraper(row["url"])
        except requests.RequestException as e:
            print(f"Napaka ({row['trgovina']}, {row['artikel']}): {e}", file=sys.stderr)

    hn_rows = [i for i, row in enumerate(rows) if host_of(row["base_url"]) == HITRINAKUP_HOST]
    if hn_rows:
        for i, price in zip(hn_rows, get_hitrinakup_prices([rows[i]["url"] for i in hn_rows])):
            prices[i] = price

    return prices


if __name__ == "__main__":
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        rows = conn.execute(QUERY).fetchall()
        prices = scrape(rows)

        last_artikel = None
        for row, price in zip(rows, prices):
            if row["artikel_id"] != last_artikel:
                print(row["artikel"])
                last_artikel = row["artikel_id"]

            if price:
                conn.execute(
                    "INSERT INTO cena (artikel_id, trgovina_id, date, price) VALUES (?, ?, ?, ?)",
                    (row["artikel_id"], row["trgovina_id"], datetime.now().isoformat(timespec="seconds"), float(price)),
                )
                print(f"  {row['trgovina']}: {price} €")
            else:
                print(f"  {row['trgovina']}: cena ni najdena")
        conn.commit()
    except (PlaywrightError, RuntimeError) as e:
        sys.exit(f"Napaka pri nalaganju strani: {e}")
    finally:
        conn.close()
