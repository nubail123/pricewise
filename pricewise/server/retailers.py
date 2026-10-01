"""Read-only public UAE storefront adapters. No retailer scripts are executed.

Only product/search pages are fetched. No account, cart or checkout APIs are used.
Prices are concrete AED listings/variants, never aggregate 'from' prices, installments,
member-only amounts or inferred prices. Unknown stock stays unknown.
"""
from __future__ import annotations

import html
import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote, urlencode, urljoin, urlparse

from bs4 import BeautifulSoup
from curl_cffi import requests

from catalog import SourceError, amount, now_iso, safe_store_url
from matching import relevance, is_accessory
from store_config import BY_ID, search_url

DETAIL_CACHE = {}
DETAIL_LOCK = threading.Lock()
DETAIL_TTL = 120
ECITY_CURRENCY = None
ECITY_LOCK = threading.Lock()
SHARAFDG_APP_ID = os.getenv("SHARAFDG_ALGOLIA_APP_ID", "9KHJLG93J1")
SHARAFDG_API_KEY = os.getenv("SHARAFDG_ALGOLIA_API_KEY", "e81d5b30a712bb28f0f1d2a52fc92dd0")
SHARAFDG_INDEX = "products_index"
EROS_APP_ID = os.getenv("EROS_ALGOLIA_APP_ID", "YJ3H8B3JUL")
EROS_API_KEY = os.getenv("EROS_ALGOLIA_API_KEY", "ZGJkNGVkMTY0NTJjMGRhMTI3M2VlMTg1MTY5OTg2ZDQ3MjM5OGZkNzgzMjMwYmMzMDJlZjY0YzgzMDIzZjZjMXRhZ0ZpbHRlcnM9")
EROS_INDEX = "magento2_default_products"


def page(url, store, timeout=12):
    try:
        response = requests.get(url, impersonate="chrome", timeout=timeout)
        if response.status_code != 200:
            raise SourceError("blocked" if response.status_code in {202, 403, 429, 503} else "error", f"{BY_ID[store]['name']} did not return a readable product page. No price was estimated.")
        if len(response.content) > 5_000_000:
            raise SourceError("error", "The retailer page is too large to safely read.")
        return response
    except SourceError:
        raise
    except Exception:
        raise SourceError("error", f"{BY_ID[store]['name']} did not respond in time.")


def rsc_records(html):
    """Decode literal JSON in Next's public server-rendered product data, never JS."""
    soup = BeautifulSoup(html, "html.parser")
    parts = []
    for tag in soup.select("script:not([src])"):
        match = re.search(r"self\.__next_f\.push\((\[.*\])\)\s*;?\s*$", tag.get_text(), re.S)
        if match:
            try:
                value = json.loads(match.group(1))
                if isinstance(value, list) and len(value) > 1 and isinstance(value[1], str):
                    parts.append(value[1])
            except (ValueError, TypeError):
                pass
    values, seen = [], set()
    decoder = json.JSONDecoder()
    # Some Flight text records have no newline terminator. Parse whole script
    # chunks too, then their joined stream for fragmented JSON records.
    for stream in [*parts, "".join(parts)]:
        for marker in re.finditer(r"(?:^|\n)[A-Za-z0-9]+:(?=[\[{])", stream):
            try:
                value, end = decoder.raw_decode(stream, marker.end())
                literal = stream[marker.end():end]
                if literal not in seen:
                    seen.add(literal)
                    values.append(value)
            except ValueError:
                pass
    return values


def walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def base_offer(store, identifier, title, price, url, checked_at, **fields):
    url = safe_store_url(url, store)
    if not identifier or not title or not amount(price) or not url or urlparse(url).path in {"", "/"}:
        return None
    reference = amount(fields.pop("originalPrice", None))
    result = {"store": store, "id": str(identifier), "title": str(title).strip(), "brand": "", "price": amount(price), "originalPrice": reference if reference and reference > amount(price) else None, "currency": "AED", "url": url, "image": None, "rating": None, "ratingCount": None, "specs": {}, "seller": BY_ID[store]["name"], "available": None, "barcode": None, "checkedAt": checked_at, "mode": "public", "priceSource": "Retailer search listing"}
    result.update(fields)
    return result


def normalize_carrefour(item, checked_at):
    if item.get("currency") != "AED" or not item.get("productName"):
        return None
    limits = item.get("orderThreshold") or {}
    if (amount(limits.get("min")) or 1) > 1:
        return None  # Do not compare a wholesale minimum with a single item.
    stock = item.get("stock") or {}
    quantity = stock.get("value")
    status = str(stock.get("stockLevelStatus") or "").lower()
    available = False if status in {"outofstock", "out_of_stock"} or quantity == 0 else True if isinstance(quantity, (int, float)) and quantity > 0 else True if status in {"instock", "lowstock"} else None
    url = item.get("productUrl") or ""
    params = {"offer": item.get("offerId"), "sid": item.get("intent"), "sellerId": item.get("shopId")}
    params = {k: str(v) for k, v in params.items() if v not in (None, "")}
    if params:
        url += ("&" if "?" in url else "?") + urlencode(params)
    title = item["productName"]
    unit = "kg" if item.get("isSoldByWeight") is True else "each"
    if unit == "kg":
        title += " · priced per kg"
    return base_offer("carrefour", item.get("productCompositeId") or item.get("productId"), title, item.get("sellingPrice"), url, checked_at, originalPrice=item.get("markedPrice"), image=item.get("imageUrl"), seller=item.get("shopName") or "Carrefour", available=available, unit=unit)


def carrefour_public(query):
    response = page(search_url("carrefour", query), "carrefour")
    nodes = [node for value in rsc_records(response.text) for node in walk(value) if node.get("productId") and "sellingPrice" in node and node.get("productName")]
    rows = [normalize_carrefour(node, now_iso()) for node in nodes]
    if not nodes and not re.search(r"no results|no products|0 products|didn't find", BeautifulSoup(response.text, "html.parser").get_text(" ", strip=True), re.I):
        raise SourceError("error", "Carrefour's product-page format changed. No prices were guessed.")
    return list({row["id"]: row for row in rows if row}.values())[:30]


def normalize_lulu(item, checked_at):
    if str(item.get("currency_type") or "").lower() != "aed" or not item.get("sku"):
        return None
    attrs = item.get("attributes") or {}
    title = str(item.get("name") or "").strip()
    for key in ("color", "storage", "storage_capacity", "regional_version"):
        value = attrs.get(key)
        if isinstance(value, str) and value.strip() and value.casefold() not in title.casefold():
            title += " · " + value.strip()
    path = item.get("absolute_url") or ""
    if str(path).startswith("/en-ae/"):
        url = path
    else:
        url = "/en-ae/" + str(path).lstrip("/")
    images = item.get("productimage_set") or []
    image = images[0].get("image") if images and isinstance(images[0], dict) else None
    in_stock = item.get("in_stock")
    available = in_stock if isinstance(in_stock, bool) else None
    unit = item.get("unit_type")
    if unit in {"kg", "g", "lt", "l"}:
        title += f" · priced per {unit}"
    specs = {"Model / SKU": attrs.get("model") or str(item["sku"])}
    if attrs.get("color"):
        specs["Color"] = attrs["color"]
    return base_offer("lulu", item["sku"], title, item.get("price"), url, checked_at, brand=str(attrs.get("brand") or ""), originalPrice=item.get("retail_price"), image=image, available=available, barcode=attrs.get("ean") or attrs.get("main_ean"), specs=specs, unit="each" if unit == "qty" else unit)


def lulu_public(query):
    retailer_query = re.sub(r"^(?:Apple|Samsung)\s+", "", query, flags=re.I)
    response = page(search_url("lulu", retailer_query), "lulu")
    nodes = [node for value in rsc_records(response.text) for node in walk(value) if node.get("sku") and node.get("absolute_url") and "currency_type" in node and "price" in node]
    rows = [normalize_lulu(node, now_iso()) for node in nodes]
    if not nodes and not re.search(r"no products|no results|0 products|All Products \(\s*0\s*\)", BeautifulSoup(response.text, "html.parser").get_text(" ", strip=True), re.I):
        raise SourceError("error", "LuLu's search-page format changed. No prices were guessed.")
    return list({row["id"]: row for row in rows if row}.values())[:24]


def cached_detail(url, loader):
    with DETAIL_LOCK:
        cached = DETAIL_CACHE.get(url)
        if cached and time.monotonic() - cached[0] < DETAIL_TTL:
            return cached[1], cached[2]
    data = loader()
    checked = now_iso()
    with DETAIL_LOCK:
        DETAIL_CACHE[url] = (time.monotonic(), data, checked)
        if len(DETAIL_CACHE) > 120:
            for key in sorted(DETAIL_CACHE, key=lambda k: DETAIL_CACHE[k][0])[:len(DETAIL_CACHE) - 120]:
                DETAIL_CACHE.pop(key, None)
    return data, checked


def qualify(query):
    # Narrow Apple's canonical model names instead of letting accessories swamp results.
    if re.match(r"^(?:airpods?|iphone|ipad|macbook)\b", query, re.I):
        return "Apple " + query
    return query


def parse_virgin(html, checked_at):
    soup = BeautifulSoup(html, "html.parser")
    rows = []
    for card in soup.select(".product-item"):
        link = card.select_one("a[data-id][data-price][href]")
        currency = card.select_one(".price__currency")
        if not link or not currency or currency.get_text(strip=True) != "AED":
            continue
        current = card.select_one(".price__value .price__number")
        price = amount(current.get_text(strip=True)) if current else amount(link.get("data-price"))
        reference_element = card.select_one(".price__value--original .price__number, .price__value--old .price__number, .price__value--was .price__number")
        reference = amount(reference_element.get_text(strip=True)) if reference_element else None
        image = card.select_one("img.product-list__image")
        row = base_offer("virgin", link.get("data-id"), link.get("data-name") or link.get("title"), price, link["href"], checked_at, brand=link.get("data-brand") or "", originalPrice=reference, image=urljoin("https://www.virginmegastore.ae", image.get("src")) if image else None)
        if row:
            rows.append(row)
    return list({row["id"]: row for row in rows}.values())


def virgin_detail(row):
    try:
        def load():
            response = page(row["url"], "virgin", timeout=7)
            soup = BeautifulSoup(response.text, "html.parser")
            candidates = []
            for script in soup.select('script[type="application/ld+json"]'):
                try:
                    candidates.extend(node for node in walk(json.loads(script.get_text())) if node.get("@type") == "Product")
                except ValueError:
                    pass
            for product in candidates:
                if str(product.get("sku")) != row["id"] and str(product.get("name") or "").casefold().split() != row["title"].casefold().split():
                    continue
                offers = product.get("offers") or {}
                if isinstance(offers, list):
                    offers = offers[0] if len(offers) == 1 else {}
                spec = offers.get("priceSpecification") or offers if isinstance(offers, dict) else {}
                if isinstance(spec, dict) and spec.get("priceCurrency") == "AED" and amount(spec.get("price")):
                    availability = str(offers.get("availability") or "").split("/")[-1]
                    return {"price": amount(spec["price"]), "available": True if availability == "InStock" else False if availability == "OutOfStock" else None, "barcode": product.get("gtin13") or product.get("gtin12")}
            return None
        detail, checked = cached_detail(row["url"], load)
        if detail:
            return {**row, **detail, "checkedAt": checked, "priceSource": "Retailer product page"}
    except SourceError:
        pass  # Preserve the actual search price; never fabricate stock on detail failure.
    return row


def virgin_public(query):
    response = page(search_url("virgin", qualify(query)), "virgin")
    rows = parse_virgin(response.text, now_iso())
    rows.sort(key=lambda row: relevance(row["title"], query), reverse=True)
    if not rows and not re.search(r"0 Products found|no results|no products found", response.text, re.I):
        raise SourceError("error", "Virgin Megastore's listing format changed. No price was guessed.")
    rows = rows[:24]
    eligible = [i for i, row in enumerate(rows) if is_accessory(query) or not is_accessory(row["title"])]
    indexes = [i for i in eligible if relevance(rows[i]["title"], query) >= .65][:5] or eligible[:5]
    with ThreadPoolExecutor(max_workers=3) as pool:
        for i, updated in zip(indexes, pool.map(virgin_detail, [rows[i] for i in indexes])):
            rows[i] = updated
    return rows


def verify_ecity_currency():
    global ECITY_CURRENCY
    with ECITY_LOCK:
        if ECITY_CURRENCY and time.monotonic() - ECITY_CURRENCY[0] < 900:
            return
        response = page("https://ecityuae.ae", "ecity")
        match = re.search(r'Shopify\.currency\s*=\s*(\{[^;]+\})', response.text)
        try:
            currency = json.loads(match.group(1)).get("active") if match else None
        except ValueError:
            currency = None
        if currency != "AED":
            raise SourceError("error", "Ecity's storefront currency could not be verified as AED. No conversion or price was guessed.")
        ECITY_CURRENCY = (time.monotonic(), "AED")


def normalize_ecity(product, checked_at):
    rows = []
    for variant in product.get("variants") or []:
        if variant.get("requires_selling_plan") or product.get("requires_selling_plan") or (variant.get("quantity_rule") or {}).get("min", 1) > 1:
            continue
        raw = variant.get("price")
        if not isinstance(raw, (int, float)) or not amount(raw):
            continue
        price = amount(raw / 100)  # Shopify Ajax concrete variant amounts are in cents.
        title = str(product.get("title") or "")
        option = str(variant.get("public_title") or variant.get("title") or "")
        if option and option != "Default Title" and option.casefold() not in title.casefold():
            title += " · " + option
        variant_id = str(variant.get("id") or "")
        url = str(product.get("url") or "") + "?" + urlencode({"variant": variant_id})
        image = variant.get("featured_image") or product.get("featured_image")
        if isinstance(image, dict):
            image = image.get("src")
        if isinstance(image, str):
            image = urljoin("https://ecityuae.ae", image)
        reference = variant.get("compare_at_price")
        reference = reference / 100 if isinstance(reference, (int, float)) else None
        available = variant.get("available")
        row = base_offer("ecity", variant_id, title, price, url, checked_at, brand=str(product.get("vendor") or ""), image=image, originalPrice=reference, available=available if isinstance(available, bool) else None, barcode=variant.get("barcode"), specs={"Model / SKU": variant.get("sku") or variant_id}, priceSource="Concrete retailer product variant")
        if row:
            rows.append(row)
    return rows


def ecity_public(query):
    verify_ecity_currency()
    params = {"q": qualify(query), "resources[type]": "product", "resources[limit]": 8, "resources[options][unavailable_products]": "show", "resources[options][fields]": "title,vendor,variants.title,variants.sku"}
    response = page("https://ecityuae.ae/search/suggest.json?" + urlencode(params), "ecity")
    try:
        data = response.json()
        products = data["resources"]["results"]["products"]
    except (ValueError, KeyError, TypeError):
        raise SourceError("error", "Ecity's search response changed. No prices were guessed.")
    if not isinstance(products, list):
        raise SourceError("error", "Ecity did not return a product list.")
    products.sort(key=lambda product: relevance(str(product.get("title") or ""), query), reverse=True)
    candidates = products[:6]
    def details(product):
        path = urlparse(str(product.get("url") or "")).path
        if not re.fullmatch(r"/products/[A-Za-z0-9_%\-]+", path):
            return []
        url = "https://ecityuae.ae" + path + ".js"
        try:
            value, checked = cached_detail(url, lambda: page(url, "ecity", timeout=7).json())
            return normalize_ecity(value, checked) if isinstance(value, dict) else []
        except (SourceError, ValueError):
            return []
    with ThreadPoolExecutor(max_workers=3) as pool:
        rows = [row for batch in pool.map(details, candidates) for row in batch]
    if candidates and not rows:
        raise SourceError("error", "Ecity's concrete variant prices could not be read. Family 'from' prices were not substituted.")
    return list({row["id"]: row for row in rows}.values())[:30]


def normalize_sharafdg(hit, checked_at):
    if not isinstance(hit, dict) or hit.get("post_status") != "publish" or hit.get("archive") in (1, "1", True) or hit.get("post_type") not in (None, "product"):
        return None
    permalink = str(hit.get("permalink") or "")
    if urlparse(permalink).hostname != "uae.sharafdg.com":
        return None  # Reject non-UAE regional storefronts so prices are strictly AED.
    sku = str(hit.get("main_sku") or hit.get("sku") or hit.get("objectID") or "").strip()
    price = amount(hit.get("price"))
    title = html.unescape(str(hit.get("post_title") or "")).replace("\u00a0", " ").strip()
    if not sku or not price or not title:
        return None
    tax = hit.get("taxonomies") if isinstance(hit.get("taxonomies"), dict) else {}
    kspec = hit.get("key_specification") if isinstance(hit.get("key_specification"), dict) else {}
    algolia_color = ((tax.get("key_attr_algolia") or {}).get("color") if isinstance(tax.get("key_attr_algolia"), dict) else None) or {}
    color = kspec.get("Color") or (algolia_color.get("en_value") if isinstance(algolia_color, dict) else None)
    if isinstance(color, str) and color.strip() and color.casefold() not in title.casefold():
        title += f" · {color.strip()}"
    brands = tax.get("product_brand") if isinstance(tax.get("product_brand"), list) else []
    brand = str(brands[0]).strip() if brands else str((tax.get("attr") or {}).get("Brand") or "").strip() if isinstance(tax.get("attr"), dict) else ""
    if brand and not title.casefold().startswith(brand.casefold()):
        title = f"{brand} {title}"
    reference = amount(hit.get("regular_price"))
    offers = hit.get("promotion_offer_json") or []
    if isinstance(offers, str):
        try:
            offers = json.loads(offers)
        except ValueError:
            offers = []
    default_offer = next((o for o in offers if isinstance(o, dict) and o.get("is_default") in (1, "1", True) and o.get("active") in (1, "1", True)), None) if isinstance(offers, list) else None
    seller = str((default_offer or {}).get("seller_name") or "Sharaf DG").strip()
    in_stock = hit.get("in_stock")
    available = True if in_stock in (1, "1", True) else False if in_stock in (0, "0", False) else None
    rr = hit.get("rating_reviews") if isinstance(hit.get("rating_reviews"), dict) else {}
    rating = float(rr["rating"]) if isinstance(rr.get("rating"), (int, float)) and not isinstance(rr.get("rating"), bool) and 0 < float(rr["rating"]) <= 5 else None
    rating_count = int(rr["reviews"]) if isinstance(rr.get("reviews"), (int, float)) and not isinstance(rr.get("reviews"), bool) and int(rr["reviews"]) >= 0 else None
    barcode = str(tax.get("ean") or tax.get("upc") or "").strip() or None
    model_number = str(hit.get("model_number") or "").strip()
    specs = {"Model / SKU": model_number or sku}
    if isinstance(color, str) and color.strip():
        specs["Color"] = color.strip()
    image = hit.get("images") if isinstance(hit.get("images"), str) else None
    return base_offer("sharafdg", sku, title, price, permalink, checked_at, brand=brand, originalPrice=reference, image=image, rating=rating, ratingCount=rating_count, specs=specs, seller=seller, available=available, barcode=barcode, catalogUpdatedAt=hit.get("updated_at") or hit.get("post_modified"))


def sharafdg_query(query, filter_expr, limit=24):
    if not re.fullmatch(r"[A-Za-z0-9]{8,16}", SHARAFDG_APP_ID) or not re.fullmatch(r"[A-Za-z0-9]{20,128}", SHARAFDG_API_KEY):
        raise SourceError("error", "Sharaf DG's public search configuration is invalid.")
    url = f"https://{SHARAFDG_APP_ID.lower()}-dsn.algolia.net/1/indexes/{quote(SHARAFDG_INDEX)}/query"
    params = urlencode({"query": query, "hitsPerPage": limit, "filters": filter_expr})
    try:
        response = requests.post(
            url, impersonate="chrome", timeout=14,
            headers={
                "X-Algolia-Application-Id": SHARAFDG_APP_ID,
                "X-Algolia-API-Key": SHARAFDG_API_KEY,
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Origin": "https://uae.sharafdg.com",
                "Referer": "https://uae.sharafdg.com/",
            },
            json={"params": params},
        )
    except Exception:
        raise SourceError("error", "Sharaf DG's live search did not respond in time.")
    if response.status_code in {401, 403, 429}:
        raise SourceError("blocked", "Sharaf DG is restricting search requests right now. No prices were guessed.")
    if response.status_code != 200:
        raise SourceError("error", "Sharaf DG could not return live prices right now.")
    try:
        data = response.json()
    except ValueError:
        raise SourceError("error", "Sharaf DG returned an unreadable search response.")
    hits = data.get("hits") if isinstance(data, dict) else None
    if not isinstance(hits, list):
        raise SourceError("error", "Sharaf DG's catalog response format changed. No prices were guessed.")
    return hits


def sharafdg_public(query):
    checked_at = now_iso()
    hits = sharafdg_query(query, "post_status:publish AND price>0 AND archive:0 AND in_stock:1", 24)
    if len(hits) < 6:
        hits = [*hits, *sharafdg_query(query, "post_status:publish AND price>0 AND archive:0 AND in_stock:0", 12)]
    rows = [normalize_sharafdg(hit, checked_at) for hit in hits]
    return list({row["id"]: row for row in rows if row}.values())[:30]


def normalize_eros(hit, checked_at):
    if not isinstance(hit, dict) or hit.get("visibility_search") in (0, "0", False):
        return None
    prices = hit.get("price")
    if not isinstance(prices, dict) or not isinstance(prices.get("AED"), dict):
        return None
    aed = prices["AED"]
    price = amount(aed.get("default"))
    sku = str(hit.get("sku") or hit.get("objectID") or "").strip()
    raw_title = html.unescape(str(hit.get("name") or "")).replace("\u00a0", " ").strip()
    if not price or not sku or not raw_title:
        return None
    parts = [p.strip() for p in raw_title.split("|") if p.strip()]
    model_part = parts[-1] if len(parts) > 1 and re.fullmatch(r"[A-Za-z0-9/\-]{4,20}", parts[-1]) else None
    title = " · ".join(parts[:-1] if model_part and len(parts) > 2 else parts)
    brand = str(hit.get("product_brand") or "").strip()
    if brand and not title.casefold().startswith(brand.casefold()):
        title = f"{brand} {title}"
    reference = amount(aed.get("default_original_formated"))
    image = hit.get("image_url") or hit.get("thumbnail_url")
    in_stock = hit.get("in_stock")
    available = True if in_stock in (1, "1", True) else False if in_stock in (0, "0", False) else None
    specs = {"Model / SKU": model_part or sku}
    return base_offer("eros", sku, title, price, hit.get("url"), checked_at, brand=brand, originalPrice=reference, image=image if isinstance(image, str) else None, specs=specs, seller="Eros Digital Home", available=available, catalogUpdatedAt=hit.get("algoliaLastUpdateAtCET"))


def eros_detail(row):
    try:
        def load():
            response = page(row["url"], "eros", timeout=7)
            soup = BeautifulSoup(response.text, "html.parser")
            unavailable = bool(soup.select_one(".stock.unavailable"))
            tocart = bool(soup.select_one("#product-addtocart-button, form#product_addtocart_form"))
            available = False if unavailable else True if tocart else None
            final_el = soup.select_one('[data-price-type="finalPrice"] .av-amount')
            page_price = amount(final_el.get_text(strip=True)) if final_el else None
            return {"price": page_price or row["price"], "available": available}
        detail, checked = cached_detail(row["url"], load)
        if detail:
            return {**row, **detail, "checkedAt": checked, "priceSource": "Retailer product page"}
    except SourceError:
        pass
    return row


def eros_public(query):
    if not re.fullmatch(r"[A-Za-z0-9]{8,16}", EROS_APP_ID) or not re.fullmatch(r"[A-Za-z0-9=_\-]{20,160}", EROS_API_KEY):
        raise SourceError("error", "Eros's public search configuration is invalid.")
    url = f"https://{EROS_APP_ID.lower()}-dsn.algolia.net/1/indexes/{quote(EROS_INDEX)}/query"
    try:
        response = requests.post(
            url, impersonate="chrome", timeout=14,
            headers={
                "X-Algolia-Application-Id": EROS_APP_ID,
                "X-Algolia-API-Key": EROS_API_KEY,
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Origin": "https://www.eros.ae",
                "Referer": "https://www.eros.ae/",
            },
            json={"params": urlencode({"query": qualify(query), "hitsPerPage": 24})},
        )
    except Exception:
        raise SourceError("error", "Eros's live search did not respond in time.")
    if response.status_code in {401, 403, 429}:
        raise SourceError("blocked", "Eros is restricting search requests right now. No prices were guessed.")
    if response.status_code != 200:
        raise SourceError("error", "Eros could not return live prices right now.")
    try:
        data = response.json()
    except ValueError:
        raise SourceError("error", "Eros returned an unreadable search response.")
    hits = data.get("hits") if isinstance(data, dict) else None
    if not isinstance(hits, list):
        raise SourceError("error", "Eros's catalog response format changed. No prices were guessed.")
    checked_at = now_iso()
    rows = [normalize_eros(hit, checked_at) for hit in hits]
    rows = list({row["id"]: row for row in rows if row}.values())
    rows.sort(key=lambda row: relevance(row["title"], query), reverse=True)
    rows = rows[:24]
    eligible = [i for i, row in enumerate(rows) if is_accessory(query) or not is_accessory(row["title"])]
    indexes = [i for i in eligible if relevance(rows[i]["title"], query) >= .55][:4] or eligible[:4]
    with ThreadPoolExecutor(max_workers=3) as pool:
        for i, updated in zip(indexes, pool.map(eros_detail, [rows[i] for i in indexes])):
            rows[i] = updated
    return rows


def extra_search(query, store):
    adapters = {"sharafdg": sharafdg_public, "carrefour": carrefour_public, "lulu": lulu_public, "virgin": virgin_public, "ecity": ecity_public, "eros": eros_public}
    try:
        return adapters[store](query)
    except SourceError:
        raise
    except Exception:
        raise SourceError("error", f"{BY_ID[store]['name']} returned no safely readable price data. No prices were estimated.")
