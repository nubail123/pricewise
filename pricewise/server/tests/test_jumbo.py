import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from jumbo import normalize_jumbo
from matching import match_score, group_products, models


def hit(**values):
    base = {"name": "Sony WH-1000XM5 Wireless Headphones Black", "sku": "WH1000XM5/B-A", "objectID": "123", "Brand": "Sony", "color": "Black", "in_stock": 1, "visibility_search": 1, "url_path": "sony-wh-1000xm5-headphones-black.html", "image_url": "https://mcprod.jumbo.ae/media/catalog/product/x.jpg", "price": {"AED": {"default": 799, "cost_formatted": "AED899.00"}}}
    base.update(values)
    return base


def offer(store, title, price=100, available=True, id=None):
    return {"store": store, "id": id or store, "title": title, "brand": "", "price": price, "available": available, "image": None, "rating": None, "specs": {}, "checkedAt": "2026-10-01T10:00:00+00:00"}


class JumboParserTests(unittest.TestCase):
    def test_current_aed_price_not_reference(self):
        row = normalize_jumbo(hit(), "now")
        self.assertEqual(row["store"], "jumbo")
        self.assertEqual(row["price"], 799)
        self.assertEqual(row["originalPrice"], 899)
        self.assertTrue(row["available"])
        self.assertEqual(row["url"], "https://www.jumbo.ae/sony-wh-1000xm5-headphones-black.html")

    def test_out_of_stock_is_explicit_not_invented_price(self):
        row = normalize_jumbo(hit(in_stock=0), "now")
        self.assertEqual(row["price"], 799)
        self.assertFalse(row["available"])

    def test_unknown_stock_is_not_called_out_of_stock(self):
        self.assertIsNone(normalize_jumbo(hit(in_stock=None), "now")["available"])

    def test_reject_another_currency_and_missing_price(self):
        self.assertIsNone(normalize_jumbo(hit(price={"USD": {"default": 200}}), "now"))
        self.assertIsNone(normalize_jumbo(hit(price={"AED": {"default": 0}}), "now"))

    def test_preserve_explicit_color_from_catalog(self):
        row = normalize_jumbo(hit(name="Sony WH1000XM5 SmokyPink", color="Smoky Pink"), "now")
        self.assertIn("Smoky Pink", row["title"])

    def test_reject_unsafe_product_link(self):
        self.assertIsNone(normalize_jumbo(hit(url_path=None, url="https://evil.example/p.html"), "now"))
        self.assertIsNone(normalize_jumbo(hit(url_path="javascript:alert(1)"), "now"))


class ComparisonSafetyTests(unittest.TestCase):
    def test_ordinal_airpods_generation_matches_correct_number(self):
        left = offer("noon", "Apple AirPods Pro 2 USB-C White")
        right = offer("jumbo", "Apple AirPods Pro (2nd generation) USB-C White")
        self.assertGreaterEqual(match_score(left, right)[0], .7)
        self.assertEqual(match_score(left, offer("jumbo", "Apple AirPods Pro (3rd generation) USB-C White"))[0], 0)

    def test_connector_variants_do_not_match(self):
        self.assertEqual(match_score(offer("noon", "Apple AirPods Pro 2 USB-C White"), offer("jumbo", "Apple AirPods Pro 2 Lightning White"))[0], 0)

    def test_watch_lte_and_bluetooth_do_not_match(self):
        self.assertEqual(match_score(offer("noon", "Samsung Galaxy Watch8 44mm LTE Silver"), offer("jumbo", "Samsung Galaxy Watch8 44mm Bluetooth Silver"))[0], 0)

    def test_macbook_chip_and_family_generations(self):
        left = offer("noon", "Apple MacBook Air M2 256GB Silver")
        right = offer("jumbo", "Apple MacBook Air M3 256GB Silver")
        self.assertEqual(match_score(left, right)[0], 0)

    def test_no_difference_for_unpurchasable_listing(self):
        left = offer("noon", "Sony WH1000XM5 Black", 799)
        right = offer("jumbo", "Sony WH1000XM5 Black", 699, available=False)
        product = group_products([left], [right], "Sony WH1000XM5")[0]
        self.assertIsNone(product["priceDifference"])
        self.assertIsNone(product["lowerStore"])
        self.assertEqual(product["offers"]["jumbo"]["price"], 699)

    def test_equal_identity_prefers_cheaper_available_listing(self):
        left = offer("noon", "Sony WH1000XM5 Headphones Black", 799)
        expensive = offer("jumbo", "Sony WH1000XM5 Headphones Black", 1299, id="expensive")
        cheap = offer("jumbo", "Sony WH1000XM5 Headphones Black", 999, id="cheap")
        product = next(p for p in group_products([left], [expensive, cheap], "headphones") if p["offers"]["noon"])
        self.assertEqual(product["offers"]["jumbo"]["id"], "cheap")

    def test_favorite_identity_is_stable_across_source_availability(self):
        left = offer("noon", "Sony WH1000XM5 Black")
        right = offer("jumbo", "Sony WH1000XM5 Black")
        self.assertEqual(group_products([left], [], "Sony")[0]["id"], group_products([left], [right], "Sony")[0]["id"])


if __name__ == "__main__":
    unittest.main()
