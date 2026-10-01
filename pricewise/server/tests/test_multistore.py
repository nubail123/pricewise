"""Synthetic fixtures only; these prices are never used by the running app."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from matching import group_catalog, match_score, canonical_barcode
from retailers import rsc_records, walk, normalize_carrefour, normalize_lulu, parse_virgin, normalize_ecity, normalize_sharafdg, normalize_eros
from catalog import amount, safe_store_url


def offer(store, title="Sony WH1000XM5 Black", price=100, available=True, barcode=None):
    return {"store": store, "id": store, "title": title, "brand": "", "price": price, "available": available, "barcode": barcode, "image": None, "specs": {}, "checkedAt": "2026-10-01T10:00:00+00:00"}


class MultiStoreTests(unittest.TestCase):
    def test_three_store_group_and_price_range(self):
        products = group_catalog({"noon": [offer("noon", price=110)], "jumbo": [offer("jumbo", price=100)], "carrefour": [offer("carrefour", price=120)]}, "Sony")
        self.assertEqual(len(products), 1)
        self.assertEqual(products[0]["offerCount"], 3)
        self.assertEqual(products[0]["priceDifference"], 20)
        self.assertEqual(products[0]["lowerStore"], "jumbo")
        self.assertEqual(products[0]["match"]["level"], "likely")

    def test_wildcard_anchor_cannot_bridge_color_conflict(self):
        products = group_catalog({"noon": [offer("noon", "Sony WH1000XM5")], "jumbo": [offer("jumbo", "Sony WH1000XM5 Black")], "lulu": [offer("lulu", "Sony WH1000XM5 Silver")]}, "Sony")
        self.assertEqual(len(products), 2)
        self.assertFalse(any(p["offerCount"] == 3 for p in products))

    def test_out_of_stock_and_unknown_prices_do_not_inflate_gap(self):
        stores = {"noon": [offer("noon", price=100)], "jumbo": [offer("jumbo", price=120)], "ecity": [offer("ecity", price=50, available=False)], "virgin": [offer("virgin", price=200, available=None)]}
        product = group_catalog(stores, "Sony")[0]
        self.assertEqual(product["priceDifference"], 20)
        self.assertEqual(product["availableOfferCount"], 2)
        self.assertEqual(product["offerCount"], 4)
        self.assertEqual(product["lowerStore"], "noon")

    def test_valid_upc_and_zero_padded_ean_are_same_identity(self):
        self.assertEqual(canonical_barcode("195950543735"), canonical_barcode("0195950543735"))
        self.assertIsNone(canonical_barcode("1234"))
        self.assertEqual(match_score(offer("ecity", "Apple AirPods Pro 3", barcode="195950543735"), offer("lulu", "Apple AirPods Pro 3", barcode="0195950543735"))[0], 1)

    def test_every_pair_must_be_verified_for_verified_group(self):
        stores = {"noon": [offer("noon", "Apple AirPods Pro 3")], "ecity": [offer("ecity", "Apple AirPods Pro 3", barcode="195950543735")], "lulu": [offer("lulu", "Apple AirPods Pro 3", barcode="0195950543735")]}
        self.assertEqual(group_catalog(stores, "AirPods")[0]["match"]["level"], "likely")

    def test_console_editions_and_grocery_quantity_conflicts(self):
        self.assertEqual(match_score(offer("noon", "Sony PlayStation 5 Slim Digital"), offer("jumbo", "Sony PlayStation 5 Slim Disc"))[0], 0)
        self.assertEqual(match_score(offer("noon", "Almarai Full Cream Milk 1L"), offer("lulu", "Almarai Full Cream Milk 2L"))[0], 0)
        self.assertEqual(match_score({**offer("noon", "Fresh Apple Gala"), "unit": "each"}, {**offer("lulu", "Fresh Apple Gala"), "unit": "kg"})[0], 0)

    def test_boolean_is_not_a_price(self):
        self.assertIsNone(amount(True))
        self.assertIsNone(amount(False))


class NewRetailerParserTests(unittest.TestCase):
    def test_public_rsc_records_survive_text_boundary_and_unicode(self):
        product = {"sku": "p1", "name": "Example\u2028Product", "price": 100, "currency_type": "aed"}
        prefix = '<script>self.__next_f.push(' + json.dumps([1, "0:T4,text"]) + ')</script>'
        payload = '<script>self.__next_f.push(' + json.dumps([1, "7:" + json.dumps({"products": [product]}) + "\n"]) + ')</script>'
        nodes = [n for record in rsc_records(prefix + payload) for n in walk(record)]
        self.assertTrue(any(n.get("sku") == "p1" for n in nodes))

    def test_carrefour_sale_price_seller_and_stock(self):
        item = {"productId": "123", "productCompositeId": "123|offer1", "productName": "Sony WH1000XM5 Black", "sellingPrice": 799, "markedPrice": 1499, "currency": "AED", "stock": {"value": 2}, "orderThreshold": {"min": 1}, "productUrl": "/mafuae/en/headphones/p/123", "shopName": "Example merchant", "offerId": "offer1", "shopId": "1"}
        row = normalize_carrefour(item, "now")
        self.assertEqual(row["price"], 799)
        self.assertEqual(row["originalPrice"], 1499)
        self.assertEqual(row["seller"], "Example merchant")
        self.assertTrue(row["available"])
        self.assertIn("offer=offer1", row["url"])
        self.assertIsNone(normalize_carrefour({**item, "currency": "SAR"}, "now"))
        self.assertIsNone(normalize_carrefour({**item, "orderThreshold": {"min": 3}}, "now"))

    def test_lulu_currency_concrete_price_and_color(self):
        item = {"sku": "1", "name": "Sony WH1000XM5", "currency_type": "aed", "price": "799.000", "retail_price": "999.000", "in_stock": False, "absolute_url": "/sony-headphones/p/1/", "attributes": {"color": "Black", "brand": "Sony"}, "unit_type": "qty"}
        row = normalize_lulu(item, "now")
        self.assertEqual(row["price"], 799)
        self.assertFalse(row["available"])
        self.assertIn("Black", row["title"])
        self.assertIn("/en-ae/", row["url"])
        self.assertIsNone(normalize_lulu({**item, "currency_type": "sar"}, "now"))

    def test_virgin_plain_search_price_does_not_invent_stock(self):
        html = '<li class="product-item"><a data-id="1" data-name="Apple AirPods Pro 3" data-brand="Apple" data-price="949" href="/en/audio/p/1"></a><div class="price__value"><span class="price__currency">AED</span><span class="price__number">949</span></div></li>'
        row = parse_virgin(html, "now")[0]
        self.assertEqual(row["price"], 949)
        self.assertIsNone(row["available"])
        self.assertEqual(parse_virgin(html.replace("AED", "SAR"), "now"), [])

    def test_ecity_uses_variant_cents_not_aggregate_from_price(self):
        product = {"title": "Apple iPhone 16", "vendor": "Apple", "url": "/products/iphone-16", "price_min": 100, "variants": [{"id": 1, "price": 294900, "compare_at_price": 299900, "title": "128GB / White", "available": True}]}
        row = normalize_ecity(product, "now")[0]
        self.assertEqual(row["price"], 2949)
        self.assertEqual(row["originalPrice"], 2999)
        self.assertIn("128GB / White", row["title"])
        self.assertIn("variant=1", row["url"])

    def test_no_subscription_or_bulk_variant_as_single_purchase(self):
        base = {"title": "Headphones", "vendor": "Sony", "url": "/products/headphones", "variants": [{"id": 1, "price": 79900, "requires_selling_plan": True}, {"id": 2, "price": 69900, "quantity_rule": {"min": 3}}]}
        self.assertEqual(normalize_ecity(base, "now"), [])

    def test_retailer_links_cannot_cross_into_arbitrary_hosts(self):
        for store in ["sharafdg", "carrefour", "lulu", "virgin", "ecity", "eros"]:
            self.assertIsNone(safe_store_url("https://evil.example/p", store))
            self.assertIsNone(safe_store_url("javascript:alert(1)", store))

    def test_eros_normalization_and_currency_guard(self):
        hit = {
            "visibility_search": 1, "sku": "11641283", "product_brand": "Apple",
            "name": "Apple AirPods Pro 3 | MFHP4ZE/A",
            "url": "https://www.eros.ae/apple-airpods-pro-3-zee-11641283.html",
            "image_url": "https://www.eros.ae/media/catalog/product/m/f/mfhp4zea_3_.jpg",
            "price": {"AED": {"default": 899, "default_original_formated": "AED 949.00"}},
        }
        row = normalize_eros(hit, "now")
        self.assertEqual(row["price"], 899)
        self.assertEqual(row["originalPrice"], 949)
        self.assertEqual(row["specs"]["Model / SKU"], "MFHP4ZE/A")
        self.assertIsNone(row["available"])
        self.assertIsNone(normalize_eros({**hit, "price": {"SAR": {"default": 899}}}, "now"))
        self.assertIsNone(normalize_eros({**hit, "visibility_search": 0}, "now"))

    def test_sharafdg_normalization_and_uae_domain_guard(self):
        hit = {
            "post_status": "publish", "archive": 0, "post_type": "product",
            "main_sku": "S500943895", "model_number": "MFHP4ZE/A",
            "post_title": "Apple AirPods\u00a0Pro\u00a03 (2025)",
            "price": 780, "regular_price": "949.00", "in_stock": 1,
            "permalink": "https://uae.sharafdg.com/product/apple-airpods-pro-3-2025/",
            "images": "https://pimcdn.sharafdg.com/cdn-cgi/image/width=300,height=300,fit=pad/images/S500943983_1",
            "key_specification": {"Color": "White"},
            "taxonomies": {"product_brand": ["Apple"], "ean": "195950543735"},
            "rating_reviews": {"rating": 4.7, "reviews": 681},
            "promotion_offer_json": [{"seller_name": "Digital Empire", "is_default": 1, "active": 1}],
        }
        row = normalize_sharafdg(hit, "now")
        self.assertEqual(row["price"], 780)
        self.assertEqual(row["originalPrice"], 949)
        self.assertEqual(row["seller"], "Digital Empire")
        self.assertTrue(row["available"])
        self.assertEqual(row["barcode"], "195950543735")
        self.assertIn("White", row["title"])
        self.assertIsNone(normalize_sharafdg({**hit, "permalink": "https://bahrain.sharafdg.com/product/p/"}, "now"))
        self.assertIsNone(normalize_sharafdg({**hit, "archive": 1}, "now"))


    def test_audit_matching_and_amount_regressions(self):
        from matching import category, is_accessory, variants
        cases = [
            ("Apple iPhone 16 128GB Black", "Apple iPhone 16 Plus 128GB Black"),
            ("Samsung Galaxy A57 Dual SIM Awesome Icyblue 8GB RAM 256GB 5G", "Samsung Galaxy A57 8GB RAM 5G Smartphone, Awesome Gray, 256 GB"),
            ("Sony PlayStation 5 Console", "Sony PlayStation 5 DualSense Wireless Controller"),
            ("Sony PlayStation 5 Digital Edition Marvel's Wolverine Limited Edition Console", "Sony Marvel's Wolverine, PlayStation 5"),
            ("Sony PlayStation 5 Disc Slim Console", "Sony PlayStation 5 Portal (CFIY1016Y-R)"),
            ("Sony PlayStation 5 Console", "Sony PlayStation 5 Console + Extra DualSense Wireless Controller"),
            ("Sony PlayStation 5 Console + Extra DualSense Wireless Controller", "Sony PlayStation 5 Digital Console White Bundle With Extra Dualsense Controller"),
            ("Sony PlayStation 5 Disc Console (Slim) With Extra Wireless Controller", "Sony PlayStation 5 Disc Console White with Extra Dualsense Controller"),
            ("ASUS Vivobook S14 Laptop Intel Core i5-13420H 512GB SSD", "ASUS Vivobook S14 Intel Core 5 210H 16GB RAM 512GB SSD"),
            ("Philips Air Fryer 3.2L NA110/00 Black", "Philips 1000 Series Air Fryer NA110/09 Black 3.2L"),
            ("dyson V15 Detect Extra Cordless Vacuum", "Dyson V15 Big Bin"),
            ("Dyson SV47 V15 Detect Absolute Iron Nickel Cordless Vacuum Cleaner", "Dyson V15 Detect Total Clean Cordless Vacuum Cleaner"),
            ("dyson Detect Submarine Wet & Dry Vacuum 660 W V15 Detect Submarine Yellow/Nickel", "Dyson V15 Detect Cordless Vacuum Cleaner - Yellow/Nickel"),
            ("Apple iPhone 16 128GB Black", "Pre-loved Apple iPhone 16 128GB Black"),
            ("Apple iPhone 16 128GB Black", "Apple iPhone 16 128GB Black Open Box"),
            ("Bose QuietComfort Ultra Headphones Gen 1 Black", "Bose QuietComfort Ultra Headphones Gen 2 Black"),
            ("Apple iPhone 16 128GB Black UAE Version", "Apple iPhone 16 128GB Black US Version"),
        ]
        for left, right in cases:
            self.assertEqual(match_score(offer("noon", left), offer("jumbo", right))[0], 0, f"{left} vs {right}")
        self.assertEqual(variants("Apple iPhone 16 128GB 5G Black")["quantity"], set())
        self.assertEqual(match_score(offer("noon", "Apple iPhone 16 128GB Black", barcode="195950543735"), offer("jumbo", "Apple iPhone 17 128GB Black", barcode="195950543735"))[0], 0)
        self.assertGreaterEqual(match_score(offer("carrefour", "Nutricook Air Fryer Slim 5L Black AFS100"), offer("lulu", "Nutricook 5L Air Fryer Black NC-AFS100"))[0], 0.7)
        self.assertEqual(category("Samsung Galaxy Watch8 44mm Bluetooth Silver"), "Wearables")
        self.assertEqual(category("Sony PlayStation 5 Slim Console"), "Gaming")
        self.assertFalse(is_accessory("Sony PlayStation 5 Console + Extra DualSense Wireless Controller"))
        self.assertTrue(is_accessory("Sony Marvel's Wolverine, PlayStation 5"))
        self.assertIsNone(amount({"value": True}))
        self.assertIsNone(amount("AED 799 or 999"))


if __name__ == "__main__":
    unittest.main()
