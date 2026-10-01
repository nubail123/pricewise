"""Live, best-effort UAE catalog adapters. Never substitutes demonstration prices.

Public retailer pages are not stable APIs. APIFY_TOKEN enables an optional,
server-side provider; the caller is responsible for permission and provider fees.
"""
from __future__ import annotations

import os
import math
import re
import threading
from datetime import datetime, timezone
from urllib.parse import quote, urlencode, urljoin, urlparse

from bs4 import BeautifulSoup
from curl_cffi import requests
from store_config import BY_ID, search_url


class SourceError(Exception):
    def __init__(self, status: str, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def amount(value):
    if isinstance(value, dict):
        value = value.get("value", value.get("amount", value.get("current")))
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return round(float(value), 2) if math.isfinite(value) and 0 < value < 10_000_000 else None
    if not isinstance(value, str):
        return None
    # AED prices use a decimal point. Reject unrelated currency values or multiple numbers.
    if re.search(r"\b(?:USD|SAR|EUR|GBP|EGP|OMR|QAR|KWD|BHD|INR)\b|[$€£]", value, re.I):
        return None
    numbers = re.findall(r"\d[\d,]*(?:\.\d+)?", value)
    if len(numbers) != 1:
        return None
    try:
        price = float(numbers[0].replace(",", ""))
        return round(price, 2) if math.isfinite(price) and 0 < price < 10_000_000 else None
    except ValueError:
        return None


def store_search(store: str, query: str) -> str:
    if store in BY_ID:
        return search_url(store, query)
    if store == "jumbo":
        return "https://www.jumbo.ae/search/" + quote(query, safe="")
    if store == "amazon":
        return "https://www.amazon.ae/s?" + urlencode({"k": query, "language": "en_AE"})
    return "https://www.noon.com/uae-en/search/?" + urlencode({"q": query})


def safe_store_url(value, store):
    info = BY_ID.get(store)
    if info:
        origin, hosts = info["home"], set(info["hosts"])
    elif store == "amazon":
        origin, hosts = "https://www.amazon.ae", {"www.amazon.ae", "amazon.ae"}
    else:
        return None
    url = urljoin(origin + "/", str(value or ""))
    try:
        parsed = urlparse(url)
        if parsed.scheme == "https" and parsed.hostname in hosts and not parsed.username and not parsed.password and parsed.port in (None, 443):
            return url
    except ValueError:
        pass
    return None


_thread_local = threading.local()


def noon_session():
    session = getattr(_thread_local, "noon_session", None)
    if session is None:
        session = requests.Session(impersonate="chrome")
        response = session.get("https://www.noon.com/uae-en/", timeout=10)
        if response.status_code != 200:
            raise SourceError("blocked", "Noon is restricting requests from this server. Try again later or connect a permitted product-data provider.")
        _thread_local.noon_session = session
    return session


def normalize_noon(hit, checked_at):
    price = amount(hit.get("sale_price")) or amount(hit.get("price"))
    if not price or not hit.get("name") or hit.get("is_buyable") is False:
        return None
    sku = str(hit.get("sku") or hit.get("catalog_sku") or "")
    if not sku:
        return None
    brand = hit.get("brand") or ""
    title = str(hit["name"]).strip()
    if brand and not title.lower().startswith(brand.lower()):
        title = f"{brand} {title}"
    slug = str(hit.get("url") or "product").strip("/")
    url = f"https://www.noon.com/uae-en/{quote(slug, safe='-')}/{quote(sku, safe='-')}/p/"
    if hit.get("offer_code"):
        url += "?" + urlencode({"o": hit["offer_code"]})
    rating = hit.get("product_rating") or {}
    reference = amount(hit.get("price"))
    image = hit.get("image_url")
    if not image and hit.get("image_key"):
        image = f"https://f.nooncdn.com/p/{hit['image_key']}.jpg"
    return {
        "store": "noon", "id": sku, "title": title, "brand": brand,
        "price": price, "originalPrice": reference if reference and reference > price else None,
        "currency": "AED", "url": url, "image": image,
        "rating": rating.get("value"), "ratingCount": rating.get("count"),
        "specs": hit.get("plp_specifications") or {},
        "seller": hit.get("store_name"), "available": True,
        "barcode": hit.get("ean") or hit.get("gtin"),
        "checkedAt": checked_at, "mode": "public",
    }


def noon_public(query: str) -> list[dict]:
    try:
        session = noon_session()
        response = session.get(
            "https://www.noon.com/_vs/nc/mp-customer-catalog-api/api/v3/search",
            params={"q": query, "limit": 36},
            headers={"accept": "application/json", "x-locale": "en-ae", "x-mp-country": "ae", "referer": "https://www.noon.com/uae-en/"},
            timeout=14,
        )
        if response.status_code != 200:
            raise SourceError("blocked" if response.status_code in {202, 403, 429, 503} else "error", "Noon could not return live prices right now. You can check the store directly.")
        try:
            data = response.json()
        except ValueError:
            raise SourceError("blocked", "Noon returned a verification page instead of product data.")
        if not isinstance(data, dict) or "hits" not in data:
            raise SourceError("error", "Noon's catalog response has changed. Prices were not guessed.")
        checked_at = now_iso()
        items = [normalize_noon(hit, checked_at) for hit in data["hits"] if isinstance(hit, dict)]
        return list({item["id"]: item for item in items if item}.values())
    except SourceError:
        raise
    except Exception:
        raise SourceError("error", "Noon's live catalog did not respond in time. Please try again.")


def parse_amazon(html: str, checked_at: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    products = []
    for card in soup.select('[data-component-type="s-search-result"][data-asin]'):
        asin = card.get("data-asin", "")
        heading = card.select_one("h2")
        title = heading.get_text(" ", strip=True) if heading else ""
        price_element = card.select_one(".a-price:not(.a-text-price) .a-offscreen")
        price = amount(price_element.get_text(strip=True)) if price_element else None
        if not price:
            whole = card.select_one(".a-price:not(.a-text-price) .a-price-whole")
            fraction = card.select_one(".a-price:not(.a-text-price) .a-price-fraction")
            if whole:
                price = amount(whole.get_text(strip=True).rstrip(".") + "." + (fraction.get_text(strip=True) if fraction else "00"))
        if not asin or not title or not price:
            continue
        image = card.select_one("img.s-image")
        rating_element = card.select_one(".a-icon-alt")
        rating = None
        if rating_element:
            match = re.search(r"(\d(?:\.\d)?)\s+out of", rating_element.get_text())
            if match:
                rating = float(match.group(1))
        review_element = card.select_one('a[href*="customerReviews"] .a-size-base')
        review_count = None
        if review_element:
            value = re.sub(r"\D", "", review_element.get_text())
            review_count = int(value) if value else None
        reference_element = card.select_one(".a-text-price .a-offscreen")
        reference = amount(reference_element.get_text(strip=True)) if reference_element else None
        products.append({
            "store": "amazon", "id": asin, "title": title, "brand": "",
            "price": price, "originalPrice": reference if reference and reference > price else None,
            "currency": "AED", "url": f"https://www.amazon.ae/dp/{quote(asin)}?language=en_AE",
            "image": image.get("src") if image else None,
            "rating": rating, "ratingCount": review_count,
            "specs": {}, "seller": None, "available": True, "barcode": None,
            "checkedAt": checked_at, "mode": "public",
        })
    return list({item["id"]: item for item in products}.values())


def amazon_public(query: str) -> list[dict]:
    try:
        response = requests.get(store_search("amazon", query), impersonate="chrome", timeout=14)
        if response.status_code != 200:
            raise SourceError("blocked" if response.status_code in {202, 403, 429, 503} else "error", "Amazon is blocking automated requests from this server. Check Amazon directly, or configure a permitted live-data provider.")
        products = parse_amazon(response.text, now_iso())
        if products:
            return products
        lower = response.text.lower()
        if any(marker in lower for marker in ("bm-verify", "awswaf", "captcha", "robot check", "verify that you're not a robot")):
            raise SourceError("blocked", "Amazon requires browser verification. No Amazon prices could be verified.")
        if "did not match any products" in lower or "no results for" in lower:
            return []
        raise SourceError("error", "Amazon returned no readable price listings. No prices were guessed.")
    except SourceError:
        raise
    except Exception:
        raise SourceError("error", "Amazon's live search did not respond in time. Please try again.")


def normalize_provider(item: dict, store: str, checked_at: str):
    if item.get("available") is False or re.search(r"out of stock|currently unavailable|temporarily unavailable", str(item.get("availabilityText") or ""), re.I):
        return None
    currency = item.get("currency")
    raw_price = item.get("price", item.get("sale_price", item.get("currentPrice")))
    if isinstance(raw_price, dict):
        currency = raw_price.get("currency", currency)
    if currency and currency not in {"AED", "د.إ", "د.إ.", "د.إ"}:
        return None
    price = amount(raw_price)
    title = item.get("title") or item.get("name") or item.get("productTitle") or item.get("productName")
    if not title or not price:
        return None
    identifier = str(item.get("asin") or item.get("sku") or item.get("id") or item.get("productId") or "")
    url = safe_store_url(item.get("url") or item.get("productUrl") or item.get("link"), store)
    if store == "amazon" and identifier and (not url or url == "https://www.amazon.ae/"):
        url = f"https://www.amazon.ae/dp/{quote(identifier)}"
    if not identifier or not url or urlparse(url).path in {"", "/"}:
        return None
    image = item.get("image") or item.get("imageUrl") or item.get("image_url")
    if isinstance(image, dict):
        image = image.get("url")
    if not image and isinstance(item.get("images"), list) and item["images"]:
        image = item["images"][0]
    if isinstance(image, dict):
        image = image.get("url")
    rating = item.get("rating") or item.get("stars") or item.get("reviewStars")
    if isinstance(rating, dict):
        rating = rating.get("value")
    try:
        rating = float(rating) if rating is not None else None
        if rating and not 0 <= rating <= 5:
            rating = None
    except (ValueError, TypeError):
        rating = None
    reference = amount(item.get("originalPrice") or item.get("listPrice"))
    scraped_at = item.get("scrapedAt") or item.get("scraped_at")
    if scraped_at:
        try:
            timestamp = datetime.fromisoformat(str(scraped_at).replace('Z', '+00:00'))
            if timestamp.tzinfo and timestamp <= datetime.now(timezone.utc):
                checked_at = timestamp.isoformat()
        except ValueError:
            pass
    return {
        "store": store, "id": identifier, "title": str(title),
        "brand": item.get("brand") or "", "price": price,
        "originalPrice": reference if reference and reference > price else None,
        "currency": "AED", "url": url, "image": image,
        "rating": rating, "ratingCount": item.get("reviewCount") or item.get("reviewsCount"),
        "specs": {}, "seller": item.get("seller"), "available": True,
        "barcode": item.get("ean") or item.get("gtin"), "checkedAt": checked_at, "mode": "provider",
    }


def apify_search(query: str, store: str) -> list[dict]:
    token = os.getenv("APIFY_TOKEN", "").strip()
    if not token:
        raise SourceError("error", "A product-data provider has not been configured.")
    if store == "amazon":
        actor = os.getenv("APIFY_AMAZON_ACTOR", "get_anything~amazon-ae-scraper")
        payload = {"searchTerms": [query], "startUrls": [], "amazonDomain": "ae", "maxProducts": 36, "maxPages": 1}
    else:
        actor = os.getenv("APIFY_NOON_ACTOR", "powerai~noon-products-search-scraper")
        payload = {"searchUrl": store_search("noon", query), "maxItems": 36}
    if not re.fullmatch(r"[\w~-]+", actor):
        raise SourceError("error", "The configured provider actor ID is invalid.")
    try:
        response = requests.post(
            f"https://api.apify.com/v2/acts/{actor}/run-sync-get-dataset-items",
            params={"timeout": 55, "format": "json", "clean": "true"},
            headers={"Authorization": f"Bearer {token}"}, json=payload, timeout=62,
        )
        if response.status_code in {401, 403}:
            raise SourceError("error", "The product-data provider rejected its credentials or actor permissions. Check the server configuration.")
        if response.status_code not in {200, 201}:
            raise SourceError("error", "The product-data provider could not complete this search. Check its usage limits and actor status.")
        rows = response.json()
        if not isinstance(rows, list):
            raise SourceError("error", "The product-data provider returned an unexpected response.")
        checked_at = now_iso()
        normalized = [normalize_provider(row, store, checked_at) for row in rows if isinstance(row, dict)]
        return list({row["id"]: row for row in normalized if row}.values())
    except SourceError:
        raise
    except Exception:
        raise SourceError("error", "The product-data provider timed out. It may still charge for a started run; check its dashboard before retrying.")


def search_catalog(query: str, store: str):
    if store not in {"noon", "jumbo", "sharafdg", "amazon", "carrefour", "lulu", "virgin", "ecity", "eros"}:
        raise SourceError("error", "This retailer adapter is not configured.")
    if store in {"sharafdg", "carrefour", "lulu", "virgin", "ecity", "eros"}:
        from retailers import extra_search
        return extra_search(query, store)
    if store == "jumbo":
        from jumbo import jumbo_public
        return jumbo_public(query)
    if store == "amazon" and os.getenv("APIFY_TOKEN", "").strip():
        return apify_search(query, store)
    try:
        return noon_public(query) if store == "noon" else amazon_public(query)
    except SourceError:
        if store == "noon" and os.getenv("APIFY_TOKEN", "").strip():
            return apify_search(query, store)
        raise
