# Pricewise — eight UAE stores, one search

The original responsive mint-and-coral design now compares **Noon, Jumbo, Sharaf DG, Carrefour UAE, LuLu Hypermarket UAE, Virgin Megastore UAE, Ecity Electronics, and Eros Digital Home**. Prices are in **AED**. All active adapters were tested with real responses; no demonstration prices are served.

## What was verified

An **Apple AirPods Pro 3** query returned a single likely-match group with actual listings from all **eight** retailers. Other tested queries include Sony WH-1000XM5, iPhone 16 128GB and Galaxy Watch 8. Not every retailer sells every product, and a successful connection does not imply a match for every search.

**No personal API key or paid-provider account is needed for the current direct connections.** Retailer formats/access can change. This is not an official partnership or guaranteed production feed. Obtain suitable permission and check retailer terms before a commercial launch.

## Connections

| Retailer | Read-only source | Important handling |
|---|---|---|
| Noon | Public UAE catalog | Current sale price; buyable listings |
| Jumbo | Public storefront search used by its website | AED only; stock is explicit; public search-only configuration stays in server memory |
| Sharaf DG | Public UAE storefront search catalog | Strictly `uae.sharafdg.com` AED listings; explicit stock, barcode, model, seller and RRP reference price |
| Carrefour UAE | Public search-page product data | Current selling price, merchant and selected offer; no bulk-minimum quotes |
| LuLu UAE | Public search-page product data | AED, explicit color/model/barcode/stock; pricing units preserved |
| Virgin UAE | Public search listings + relevant product-page structured data | Product-page stock when reported; unknown stock stays unknown |
| Ecity | Public search + concrete Shopify product variants | Variant prices, not aggregate 'from' prices; cents converted to AED; subscription-only/bulk variants excluded |
| Eros Digital Home | Public UAE storefront search catalog + product-page stock checks | AED only; reference prices preserved; top-candidate product pages checked for add-to-cart stock status |

No retailer scripts are executed by the backend. No account, cart, checkout or customer endpoints are used. Retailer scripts/trackers are not loaded into the user's browser. Amazon is not an active source because the tested automated access did not return usable prices. Emax was also blocked in the expansion check; unavailable retailers were not added as empty comparison columns.

## Features

- One query searches all active retailers concurrently.
- Cards show the three leading available prices, with a button to reveal the complete comparison.
- Compact multi-store table with price, reported stock, seller, listing details, timestamps and direct retailer links.
- Lowest-listed-price highlighting and an in-stock listed-price gap (highest minus lowest), **not guaranteed checkout savings**.
- Out-of-stock and unconfirmed-stock prices are visible but excluded from the price gap.
- All-retailer and 2+ store filters, individual retailer filters, sorting, price/rating filters and grid/list views.
- CSV export includes each retailer's price, stock, retrieval time and URL.
- Browser-local favorites/history; older Noon/Jumbo snapshots are retained without relabeling another store's prices.
- Mobile layouts, keyboard shortcuts, modal focus trapping and reduced-motion support.
- Same-origin API, bounded allowlisted image proxy, local fonts and no frontend analytics.

## Matching rules

Every pair in a group must pass known variant checks. An unspecified-color anchor cannot bridge a black listing and a silver listing. Known model/family, generation, capacity, size, color, region, condition, connector, watch network, console edition, pack and quantity/unit differences are rejected.

A title/model group is **likely**, not verified identical. Only valid shared GTIN barcodes across every cross-store pair yield a verified group; valid UPC/EAN leading-zero equivalents are recognized. Missing specifications remain uncertain. Compare full listing details, warranties, regional versions and seller conditions.

## Run

Requirements: Python 3.10+ and Node.js 20+.

```bash
pip install -r requirements.txt
npm install
npm run dev
```

Open `http://localhost:5173`. Vite binds **0.0.0.0:5173**, the development API binds **0.0.0.0:8000**, and `/api` uses the Vite proxy. Browser-facing code never calls a separate localhost service.

### Production

```bash
npm run build
PORT=8000 npm start
```

FastAPI serves the built `site/` and `/api` from one origin. Put the deployment behind HTTPS. In-memory caches/rate limits are appropriate for a single-instance MVP, not a high-volume public deployment; add shared caching, monitoring, deployment controls and appropriate permissions before a broad launch.

### Optional Docker

```bash
docker build -t pricewise .
docker run --rm -p 8000:8000 pricewise
```

The Docker definition includes the shared retailer registry in both build/runtime stages. It has not been built/tested in this workspace. Secrets are not baked into the image.

## Tests

```bash
npm test
npm run build
```

Synthetic unit/API fixtures are used **only in tests**, never as running-app prices. Coverage includes the eight-store API contract, missing sources, conservative pairwise grouping, valid barcode identity, quantities/console editions, regional/capacity/color/generation conflicts, AED prices, reference amounts, availability, concrete Ecity variants, Sharaf DG and Eros UAE normalization, public Next data parsing, safe links/images and cache behavior. Browser checks use the real backend and live retailer data.

## API

- `GET /api/health` — active retailer/source status; never returns search keys or credentials.
- `GET /api/search?q=product` — real grouped listings and source metadata.
- `GET /api/search?q=product&refresh=true` — bypass the query cache; failed-source cooldowns remain.
- `GET /api/featured` — four live product-model queries for the homepage.
- `GET /api/image?url=...` — approved HTTPS retailer image CDNs only; no redirects or arbitrary hosts.
- `GET /api/docs` — API documentation.

Search snapshots are cached for up to **3 minutes**. Short product-detail caching preserves the original retrieval time and does not gain another full cache period when entering a new query. Retailer indices/pages may update on the retailer's own schedule; a retrieval time is not a guarantee that the underlying price changed then.

## Price, availability and privacy

Prices are public listed amounts, not checkout quotes. Delivery fees, coupons, memberships, conditional promotions, warranties and seller conditions are not included. Stock and delivery can vary by address; country/locale is UAE and retailer default delivery context may apply. Confirm the final total on the retailer website.

Saved prices are snapshots, not background alerts. Use **Recheck this product** before buying. Favorites and recent queries stay in browser local storage. Search terms go to this backend and the connected retailers. Hosting may retain ordinary request logs. Clearing browser data removes favorites/history.

The earlier Amazon/parser/provider helpers remain in `server/catalog.py` for reference, but the default API/UI only search the eight registered retailers. Leave `APIFY_TOKEN` unset for the direct setup. If deliberately configured, it can enable a Noon fallback and provider fees may apply.

## Project map / adding another retailer

```
retailers.json          Public retailer registry shared by React and Python
src/App.jsx            Interface and browser-local state
src/styles.css         Original responsive design + compact comparisons
server/store_config.py Registry loader and search URL helper
server/app.py          API, caching, rate limits and image proxy
server/catalog.py      Shared normalization / Noon / adapter dispatch
server/jumbo.py        Jumbo public storefront adapter
server/retailers.py     Sharaf DG, Carrefour, LuLu, Virgin, Ecity and Eros adapters
server/matching.py     Pairwise variant-safe grouping and availability-aware gaps
server/tests/          Unit/API tests
```

To add a retailer, first verify real AED product/variant prices and safe stock handling; implement/test its read-only adapter, register its public metadata, add only its necessary image hosts, then live-test before enabling it. Adding a name/logo alone is not a working integration.

The headphone hero is AI-generated editorial artwork, not a retailer listing. Result images come from the retailer CDN. DM Sans and Manrope are bundled under the SIL Open Font License, with notices in `public/fonts/`.
