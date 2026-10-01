import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from matching import match_score, group_products, models, is_accessory
from catalog import amount, normalize_noon, parse_amazon, normalize_provider, safe_store_url


def offer(store, title, price=100, barcode=None):
    return {"store": store, "id": store, "title": title, "brand": "", "price": price, "barcode": barcode, "available": True, "image": None, "rating": None, "specs": {}, "checkedAt": "2026-10-01T10:00:00+00:00"}


class MatchingTests(unittest.TestCase):
    def test_model_match_is_not_verified(self):
        a = offer("noon", "Sony WH-1000XM5 Wireless Noise Cancelling Headphones Black")
        b = offer("jumbo", "Sony WH1000XM5 Wireless Headphones Black", 125)
        score, _ = match_score(a, b)
        self.assertGreaterEqual(score, 0.7)
        products = group_products([a], [b], "sony wh1000xm5")
        self.assertEqual(len(products), 1)
        self.assertEqual(products[0]["match"]["level"], "likely")
        self.assertEqual(products[0]["priceDifference"], 25)

    def test_model_generations_do_not_match(self):
        a = offer("noon", "Sony WH-1000XM5 Black")
        b = offer("jumbo", "Sony WH-1000XM6 Black")
        self.assertEqual(match_score(a, b)[0], 0)

    def test_capacity_color_condition_and_region(self):
        base = offer("noon", "Apple iPhone 16 128GB Black UAE")
        for title in ["Apple iPhone 16 256GB Black UAE", "Apple iPhone 16 128GB White UAE", "Apple iPhone 16 128GB Black UAE Renewed", "Apple iPhone 16 128GB Black International"]:
            self.assertEqual(match_score(base, offer("jumbo", title))[0], 0, title)

    def test_accessories_not_matched_to_core_product(self):
        self.assertEqual(match_score(offer("noon", "Apple iPhone 16 128GB"), offer("jumbo", "Apple iPhone 16 Case Cover"))[0], 0)

    def test_bundled_charging_case_is_not_an_accessory(self):
        self.assertFalse(is_accessory("Apple AirPods Pro 2 With MagSafe Charging Case White"))
        self.assertTrue(is_accessory("Silicone Case Cover for Apple AirPods Pro 2"))

    def test_storage_units_and_bundles(self):
        self.assertEqual(match_score(offer("noon", "Laptop 1TB"), offer("jumbo", "Laptop 1GB"))[0], 0)
        self.assertEqual(match_score(offer("noon", "PlayStation 5 Slim"), offer("jumbo", "PlayStation 5 Slim Bundle"))[0], 0)

    def test_barcode_is_verified(self):
        a = offer("noon", "Sony WH1000XM5 Black", barcode="4548736132603")
        b = offer("jumbo", "Sony WH1000XM5 Black", barcode="4548736132603")
        self.assertEqual(group_products([a], [b], "headphones")[0]["match"]["level"], "verified")

    def test_missing_store_has_no_savings(self):
        p = group_products([offer("noon", "Apple AirPods Pro 2")], [], "airpods")[0]
        self.assertIsNone(p["priceDifference"])
        self.assertIsNone(p["offers"]["jumbo"])
        self.assertIsNone(p["lowerStore"])


class ParserTests(unittest.TestCase):
    def test_aed_parser_and_currency(self):
        self.assertEqual(amount("AED 1,299.50"), 1299.5)
        self.assertIsNone(amount("USD 499.99"))
        self.assertIsNone(amount("$499"))
        self.assertIsNone(amount("Not available"))

    def test_non_finite_price_rejected(self):
        self.assertIsNone(amount(float('inf')))
        self.assertIsNone(amount(float('nan')))

    def test_documented_noon_provider_schema(self):
        row = normalize_provider({"productId": "N1234A", "productName": "Wireless Headphones", "price": "AED 799.00", "productUrl": "https://www.noon.com/uae-en/wireless-headphones/N1234A/p/", "imageUrl": "https://f.nooncdn.com/p/test.jpg", "scrapedAt": "2026-02-10T06:12:11.375Z"}, "noon", "now")
        self.assertEqual(row["price"], 799)
        self.assertEqual(row["id"], "N1234A")
        self.assertTrue(row["checkedAt"].startswith("2026-02-10"))

    def test_noon_sale_price_is_current(self):
        row = normalize_noon({"sku": "N1", "name": "Headphones", "brand": "Sony", "price": 1299, "sale_price": 799, "is_buyable": True}, "now")
        self.assertEqual(row["price"], 799)
        self.assertEqual(row["originalPrice"], 1299)
        self.assertIn("www.noon.com/uae-en/", row["url"])

    def test_amazon_markup(self):
        html = '<div data-component-type="s-search-result" data-asin="B012345678"><h2><span>Sony Headphones</span></h2><span class="a-price"><span class="a-offscreen">AED 899.00</span></span><img class="s-image" src="https://m.media-amazon.com/a.jpg"><span class="a-icon-alt">4.6 out of 5 stars</span></div>'
        rows = parse_amazon(html, "now")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["price"], 899)
        self.assertEqual(rows[0]["rating"], 4.6)

    def test_no_prices_from_challenge(self):
        self.assertEqual(parse_amazon('<html><title>Robot check</title></html>', "now"), [])

    def test_provider_currency_and_links(self):
        base = {"asin": "B012345678", "title": "Headphones", "price": {"value": 400, "currency": "AED"}}
        self.assertEqual(normalize_provider(base, "amazon", "now")["price"], 400)
        self.assertIsNone(normalize_provider({**base, "price": {"value": 400, "currency": "USD"}}, "amazon", "now"))
        self.assertIsNone(safe_store_url("https://amazon.ae.evil.example/p", "amazon"))
        self.assertIsNone(safe_store_url("javascript:alert(1)", "amazon"))


if __name__ == "__main__":
    unittest.main()
