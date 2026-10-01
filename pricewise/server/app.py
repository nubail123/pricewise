from __future__ import annotations

import copy
import hashlib
import io
import os
import threading
import time
from datetime import datetime, timezone
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from PIL import Image, UnidentifiedImageError
from curl_cffi import requests

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

from catalog import SourceError, now_iso, search_catalog, store_search
from matching import group_catalog, is_accessory
from store_config import STORE_IDS, RETAILERS

app = FastAPI(title="Pricewise UAE", docs_url="/api/docs", redoc_url=None)
CACHE_TTL = 180
CACHE = {}
FEATURED_CACHE = None
CACHE_LOCK = threading.RLock()
QUERY_LOCKS = defaultdict(threading.Lock)
SOURCE_POOL = ThreadPoolExecutor(max_workers=16)
STORES = STORE_IDS
SOURCE_LOCKS = {store: threading.Lock() for store in STORES}
SOURCE_FAILURES = {}
LAST_SOURCES = {}
REQUEST_TIMES = defaultdict(deque)
RATE_LOCK = threading.Lock()
IMAGE_DIR = ROOT / "data" / "images"
IMAGE_DIR.mkdir(parents=True, exist_ok=True)
IMAGE_HOSTS = {"f.nooncdn.com", "a.nooncdn.com", "m.media-amazon.com", "images-na.ssl-images-amazon.com", "mcprod.jumbo.ae", "www.jumbo.ae", "pimcdn.sharafdg.com", "cmsimg.sdgcdn.com", "cdn.mafrservices.com", "bf1af2.akinoncloudcdn.com", "www.virginmegastore.ae", "cdn.shopify.com", "ecityuae.ae", "www.eros.ae", "eros.ae"}


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if request.url.path.startswith("/api/") and not request.url.path.startswith("/api/image"):
        response.headers["Cache-Control"] = "no-store"
    return response


def rate_limit(request: Request):
    key = request.client.host if request.client else "unknown"
    now = time.monotonic()
    with RATE_LOCK:
        events = REQUEST_TIMES[key]
        while events and events[0] < now - 60:
            events.popleft()
        if len(events) >= 24:
            raise HTTPException(429, "Too many searches. Please wait a minute before trying again.", headers={"Retry-After": "60"})
        events.append(now)
        if len(REQUEST_TIMES) > 1000:
            for client in list(REQUEST_TIMES):
                if not REQUEST_TIMES[client] or REQUEST_TIMES[client][-1] < now - 120:
                    del REQUEST_TIMES[client]


def fetch_source(query, store):
    metadata = {"store": store, "status": "unknown", "itemCount": 0, "checkedAt": now_iso(), "searchUrl": store_search(store, query), "mode": "public"}
    with SOURCE_LOCKS[store]:
        failure = SOURCE_FAILURES.get(store)
        if failure and time.monotonic() - failure[0] < CACHE_TTL:
            previous = copy.deepcopy(failure[1])
            previous["searchUrl"] = metadata["searchUrl"]
            previous["cooldown"] = True
            return [], previous
        try:
            items = search_catalog(query, store)
            in_stock = sum(item.get("available") is True for item in items)
            metadata.update(status="ok" if items else "empty", itemCount=len(items), inStockCount=in_stock, checkedAt=now_iso(), message=f"{len(items)} priced listings returned; {in_stock} marked in stock. Out-of-stock listings are labeled and excluded from price-difference calculations." if items else "No eligible priced listings were returned for this search.")
            if items:
                metadata["mode"] = items[0].get("mode", "public")
            SOURCE_FAILURES.pop(store, None)
        except SourceError as error:
            items = []
            metadata.update(status=error.status, message=error.message, checkedAt=now_iso())
            SOURCE_FAILURES[store] = (time.monotonic(), copy.deepcopy(metadata))
        except Exception:
            items = []
            metadata.update(status="error", message="This store could not return readable prices. Please try again later.", checkedAt=now_iso())
        with CACHE_LOCK:
            LAST_SOURCES[store] = copy.deepcopy(metadata)
        return items, metadata


def cache_mark(result):
    ages = []
    now = datetime.now(timezone.utc)
    for product in result.get("products", []):
        for offer in product.get("offers", {}).values():
            if offer and offer.get("checkedAt"):
                try:
                    ages.append(max(0, (now - datetime.fromisoformat(offer["checkedAt"].replace("Z", "+00:00"))).total_seconds()))
                except (ValueError, TypeError):
                    pass
    # A cached product detail cannot gain an extra three minutes by entering a
    # new query cache. Preserve its retrieval time and cap total cache age.
    return time.monotonic() - min(CACHE_TTL, max(ages, default=0))


def search(query, refresh=False):
    query = " ".join(query.split())
    key = query.casefold()
    with QUERY_LOCKS[key]:
        with CACHE_LOCK:
            cached = CACHE.get(key)
            if cached and not refresh and time.monotonic() - cached[0] < CACHE_TTL:
                result = copy.deepcopy(cached[1])
                result["cached"] = True
                return result
        futures = {store: SOURCE_POOL.submit(fetch_source, query, store) for store in STORES}
        fetched = {store: futures[store].result() for store in STORES}
        result = {
            "query": query, "currency": "AED", "country": "AE", "checkedAt": now_iso(),
            "cached": False, "cacheSeconds": CACHE_TTL,
            "sources": [fetched[store][1] for store in STORES], "retailers": RETAILERS,
            "products": group_catalog({store: fetched[store][0] for store in STORES}, query),
        }
        with CACHE_LOCK:
            CACHE[key] = (cache_mark(result), copy.deepcopy(result))
            if len(CACHE) > 100:
                oldest = sorted(CACHE, key=lambda q: CACHE[q][0])[:len(CACHE) - 100]
                for old in oldest:
                    del CACHE[old]
        return result


@app.get("/api/health")
def health():
    with CACHE_LOCK:
        sources = copy.deepcopy(LAST_SOURCES)
    return {
        "status": "ok", "country": "AE", "currency": "AED",
        "providerConfigured": bool(os.getenv("APIFY_TOKEN", "").strip()), "retailers": RETAILERS,
        "sources": [sources.get(store, {"store": store, "status": "unknown", "message": "Not checked yet.", "mode": "public"}) for store in STORES],
        "cacheSeconds": CACHE_TTL,
    }


@app.get("/api/search")
def api_search(request: Request, q: str = Query(..., min_length=2, max_length=120), refresh: bool = False):
    rate_limit(request)
    query = " ".join(q.split())
    if len(query) < 2 or not any(char.isalnum() for char in query):
        raise HTTPException(400, "Enter a product name with at least two letters or numbers.")
    if any(ord(char) < 32 for char in query):
        raise HTTPException(400, "The search contains invalid characters.")
    return search(query, refresh)


FEATURE_QUERIES = ["Apple AirPods Pro 3", "Sony WH-1000XM5", "Apple iPhone 16 128GB", "Samsung Galaxy Watch 8"]


@app.get("/api/featured")
def featured(request: Request):
    global FEATURED_CACHE
    rate_limit(request)
    with CACHE_LOCK:
        if FEATURED_CACHE and time.monotonic() - FEATURED_CACHE[0] < CACHE_TTL:
            result = copy.deepcopy(FEATURED_CACHE[1])
            result["cached"] = True
            return result
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(search, FEATURE_QUERIES))
    products, source_map = [], {}
    for result in results:
        eligible = [product for product in result["products"] if product["relevance"] >= 0.75 and not is_accessory(product["title"])]
        if eligible:
            products.append(eligible[0])
        for source in result["sources"]:
            current = source_map.get(source["store"])
            if current is None or source["status"] == "ok":
                source_map[source["store"]] = source
    result = {"query": "Featured picks", "currency": "AED", "country": "AE", "checkedAt": now_iso(), "cached": False, "cacheSeconds": CACHE_TTL, "sources": list(source_map.values()), "products": products}
    with CACHE_LOCK:
        FEATURED_CACHE = (cache_mark(result), copy.deepcopy(result))
    return result


@app.get("/api/image")
def product_image(url: str = Query(..., max_length=2000)):
    try:
        parsed = urlparse(url)
        valid = parsed.scheme == "https" and parsed.hostname in IMAGE_HOSTS and parsed.port in (None, 443) and not parsed.username and not parsed.password
    except ValueError:
        valid = False
    if not valid:
        raise HTTPException(400, "Only HTTPS product images from approved retailer CDNs are allowed.")
    digest = hashlib.sha256(url.encode()).hexdigest()
    path = IMAGE_DIR / f"{digest}.webp"
    if path.is_file():
        return FileResponse(path, media_type="image/webp", headers={"Cache-Control": "public, max-age=86400"})
    try:
        # No redirect-following: the allowlist must also protect against redirects.
        remote = requests.get(url, timeout=8, allow_redirects=False)
        if remote.status_code != 200 or not remote.headers.get("content-type", "").lower().startswith("image/"):
            raise HTTPException(502, "The retailer image is unavailable.")
        if len(remote.content) > 5_000_000:
            raise HTTPException(413, "The retailer image is too large.")
        image = Image.open(io.BytesIO(remote.content))
        if image.width * image.height > 30_000_000:
            raise HTTPException(413, "The retailer image is too large.")
        image.thumbnail((600, 600))
        if image.mode not in ("RGB", "RGBA"):
            image = image.convert("RGB")
        buffer = io.BytesIO()
        image.save(buffer, format="WEBP", quality=87)
        content = buffer.getvalue()
        path.write_bytes(content)
        # Bounded cache; images contain no credentials or user information.
        files = list(IMAGE_DIR.glob("*.webp"))
        if len(files) > 150:
            for old in sorted(files, key=lambda f: f.stat().st_mtime)[:len(files) - 150]:
                old.unlink(missing_ok=True)
        return Response(content, media_type="image/webp", headers={"Cache-Control": "public, max-age=86400"})
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError):
        raise HTTPException(502, "The retailer image could not be displayed.")
    except Exception:
        raise HTTPException(502, "The retailer image did not respond.")


# `npm run build` creates a same-origin production site; no frontend localhost URLs.
SITE = ROOT / "site"
if SITE.is_dir():
    app.mount("/assets", StaticFiles(directory=SITE / "assets"), name="assets")

    @app.get("/{path:path}")
    def frontend(path: str):
        if path.startswith("api/"):
            raise HTTPException(404, "Unknown API route.")
        candidate = (SITE / path).resolve()
        if candidate.is_relative_to(SITE.resolve()) and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(SITE / "index.html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("API_PORT", os.getenv("PORT", "8000"))), log_level="info")
