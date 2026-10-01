"""Jumbo UAE's public storefront search, as used by its own website.

Reads the public, search-only storefront configuration from Jumbo's page.
Never evaluates JavaScript, uses account credentials, or accesses cart/customer APIs.
Prices are the AED search-listing prices returned by the retailer, not checkout quotes.
"""
from __future__ import annotations

import re
import threading
import time
from urllib.parse import quote, urlparse

import chompjs
from bs4 import BeautifulSoup
from curl_cffi import requests

from catalog import SourceError, amount, now_iso, safe_store_url

CONFIG_LOCK = threading.Lock()
CONFIG_CACHE = None
CONFIG_TTL = 1800
INDEX = "staging_en_products"  # The public index used by www.jumbo.ae's search UI.


def storefront_config(refresh=False):
    global CONFIG_CACHE
    with CONFIG_LOCK:
        if CONFIG_CACHE and not refresh and time.monotonic() - CONFIG_CACHE[0] < CONFIG_TTL:
            return CONFIG_CACHE[1]
        try:
            response = requests.get("https://www.jumbo.ae/search/headphones", impersonate="chrome", timeout=14)
            if response.status_code != 200:
                raise SourceError("blocked", "Jumbo is restricting storefront requests from this server. No price was estimated.")
            soup = BeautifulSoup(response.text, "html.parser")
            script = next((tag.get_text() for tag in soup.select("script:not([src])") if "window.__INITIAL_STATE__" in tag.get_text()), None)
            if not script:
                raise SourceError("error", "Jumbo's storefront configuration is not readable right now.")
            # A literal-data parser only: retailer JavaScript is NEVER executed.
            state = chompjs.parse_js_object(script)
            public = state.get("config", {}).get("algolia", {})
            app_id = str(public.get("app_id") or "")
            search_key = str(public.get("api_key") or "")
            if not re.fullmatch(r"[A-Za-z0-9]{8,16}", app_id) or not re.fullmatch(r"[A-Za-z0-9]{20,128}", search_key):
                raise SourceError("error", "Jumbo's public search configuration has changed. No prices were guessed.")
            result = {"app_id": app_id, "search_key": search_key}
            CONFIG_CACHE = (time.monotonic(), result)
            return result
        except SourceError:
            raise
        except Exception:
            raise SourceError("error", "Jumbo's storefront did not return usable search configuration in time.")


def normalize_jumbo(hit, checked_at):
    title = str(hit.get("name") or "").strip()
    sku = str(hit.get("sku") or hit.get("objectID") or "").strip()
    prices = hit.get("price")
    # Reject another currency; do not silently convert regional prices to AED.
    if not title or not sku or not isinstance(prices, dict) or not isinstance(prices.get("AED"), dict):
        return None
    aed = prices["AED"]
    price = amount(aed.get("default"))
    if not price or hit.get("visibility_search") in (0, "0", False):
        return None
    path = hit.get("url_path")
    if not path:
        try:
            parsed = urlparse(str(hit.get("url") or ""))
            if parsed.hostname not in {"www.jumbo.ae", "jumbo.ae", "mcprod.jumbo.ae"}:
                return None
            path = parsed.path
        except ValueError:
            return None
    url = safe_store_url(str(path).lstrip("/"), "jumbo")
    if not url or urlparse(url).path in {"", "/"}:
        return None
    color = str(hit.get("color") or "").strip()
    if color and color.casefold() not in title.casefold():
        title += f" · {color}"  # Explicit retailer color, not an inferred variant.
    brand = hit.get("Brand") or ""
    if brand and not title.casefold().startswith(str(brand).casefold()):
        title = f"{brand} {title}"
    # `cost_formatted` is the reference/strike-through amount in the storefront.
    reference = amount(aed.get("cost_formatted")) or amount(hit.get("cost"))
    image = hit.get("image_url") or hit.get("thumbnail_url")
    specs = {"Model / SKU": sku}
    if color:
        specs["Color"] = color
    if hit.get("FamilyType"):
        specs["Product type"] = hit["FamilyType"]
    rating = hit.get("rating_summary")
    try:
        rating = float(rating) / 20 if rating is not None and 0 < float(rating) <= 100 else None
    except (TypeError, ValueError):
        rating = None
    return {
        "store": "jumbo", "id": str(hit.get("objectID") or sku), "title": title,
        "brand": str(brand), "price": price,
        "originalPrice": reference if reference and reference > price else None,
        "currency": "AED", "url": url, "image": image,
        "rating": rating, "ratingCount": None,
        "specs": specs, "seller": "Jumbo", "available": True if hit.get("in_stock") in (1, "1", True) else False if hit.get("in_stock") in (0, "0", False) else None,
        "barcode": None, "checkedAt": checked_at, "mode": "public",
        "priceSource": "Retailer search listing",
        "catalogUpdatedAt": hit.get("algoliaLastUpdateAtCET"),
    }


def jumbo_public(query):
    try:
        for attempt in range(2):
            config = storefront_config(refresh=attempt == 1)
            # Fixed, validated public read-only search destination; no arbitrary URLs.
            url = f"https://{config['app_id'].lower()}-dsn.algolia.net/1/indexes/{quote(INDEX)}/query"
            response = requests.post(
                url, impersonate="chrome", timeout=15,
                headers={
                    "X-Algolia-Application-Id": config["app_id"],
                    "X-Algolia-API-Key": config["search_key"],
                    "Content-Type": "application/json",
                    "Referer": "https://www.jumbo.ae/", "Origin": "https://www.jumbo.ae",
                },
                json={"query": query, "page": 0, "hitsPerPage": 24, "facetFilters": ["visibility_search:1"]},
            )
            if response.status_code in {401, 403} and attempt == 0:
                continue  # Refresh possibly rotated PUBLIC search config once.
            break
        if response.status_code != 200:
            raise SourceError("blocked" if response.status_code in {401, 403, 429} else "error", "Jumbo could not return its live search listings. No missing price was estimated.")
        data = response.json()
        if not isinstance(data, dict) or not isinstance(data.get("hits"), list):
            raise SourceError("error", "Jumbo's catalog response has changed. No prices were guessed.")
        checked_at = now_iso()
        rows = [normalize_jumbo(hit, checked_at) for hit in data["hits"] if isinstance(hit, dict)]
        return list({row["id"]: row for row in rows if row}.values())
    except SourceError:
        raise
    except Exception:
        raise SourceError("error", "Jumbo's live search did not respond with usable price data in time. Please try again.")
