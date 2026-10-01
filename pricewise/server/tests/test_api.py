import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as server
from catalog import SourceError
from fastapi.testclient import TestClient


def test_offer(store):
    return {"store": store, "id": store + "123", "title": "Sony WH-1000XM5 Wireless Headphones Black", "brand": "Sony", "price": 799 if store == "noon" else 849, "originalPrice": None, "currency": "AED", "url": "https://www.noon.com/uae-en/product/N1/p/" if store == "noon" else "https://www.jumbo.ae/sony-wh-1000xm5-headphones.html", "image": None, "rating": 4.5, "ratingCount": 10, "specs": {}, "seller": "test fixture", "available": True, "barcode": None, "checkedAt": server.now_iso(), "mode": "public"}


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(server.app)
        server.CACHE.clear()
        server.REQUEST_TIMES.clear()
        server.LAST_SOURCES.clear()
        server.SOURCE_FAILURES.clear()
        self.environment = patch.dict(os.environ, {"APIFY_TOKEN": ""})
        self.environment.start()

    def tearDown(self):
        self.environment.stop()
        self.client.close()

    def test_live_result_contract_and_cache(self):
        with patch.object(server, "search_catalog", side_effect=lambda query, store: [test_offer(store)]) as adapter:
            first = self.client.get("/api/search", params={"q": "Sony WH-1000XM5"}).json()
            second = self.client.get("/api/search", params={"q": "Sony WH-1000XM5"}).json()
            self.assertEqual(len(first["products"]), 1)
            self.assertEqual(first["products"][0]["priceDifference"], 50)
            self.assertEqual(first["products"][0]["match"]["level"], "likely")
            self.assertTrue(second["cached"])
            self.assertEqual(adapter.call_count, len(server.STORES))
            self.assertEqual(first["products"][0]["checkedAt"], second["products"][0]["checkedAt"])

    def test_source_block_has_no_fabricated_price(self):
        def adapter(query, store):
            if store != "noon":
                raise SourceError("blocked", "Test retailer block")
            return [test_offer(store)]
        with patch.object(server, "search_catalog", side_effect=adapter):
            response = self.client.get("/api/search", params={"q": "headphones"})
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertEqual(data["sources"][1]["status"], "blocked")
            self.assertIsNone(data["products"][0]["offers"]["jumbo"])
            self.assertIsNone(data["products"][0]["priceDifference"])

    def test_invalid_queries(self):
        self.assertEqual(self.client.get("/api/search", params={"q": "a"}).status_code, 422)
        self.assertEqual(self.client.get("/api/search", params={"q": "!!"}).status_code, 400)
        self.assertEqual(self.client.get("/api/search", params={"q": " " * 3}).status_code, 400)
        self.assertEqual(self.client.get("/api/search", params={"q": "a" * 121}).status_code, 422)

    def test_image_allowlist(self):
        for url in ["http://127.0.0.1/secret", "https://evil.example/image.jpg", "https://f.nooncdn.com.evil.example/p.jpg", "https://user:pass@f.nooncdn.com/p.jpg", "https://f.nooncdn.com:8443/p.jpg"]:
            self.assertEqual(self.client.get("/api/image", params={"url": url}).status_code, 400, url)

    def test_health_never_returns_token(self):
        with patch.dict(os.environ, {"APIFY_TOKEN": "test-not-a-real-token"}):
            response = self.client.get("/api/health")
            self.assertTrue(response.json()["providerConfigured"])
            self.assertNotIn("test-not-a-real-token", response.text)


if __name__ == "__main__":
    unittest.main()
