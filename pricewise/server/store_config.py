"""Single public retailer registry shared with the React interface."""
import json
from pathlib import Path
from urllib.parse import quote

RETAILERS = json.loads((Path(__file__).resolve().parents[1] / "retailers.json").read_text())
STORE_IDS = tuple(item["id"] for item in RETAILERS)
BY_ID = {item["id"]: item for item in RETAILERS}


def search_url(store, query):
    return BY_ID[store]["search"].replace("{query}", quote(query, safe=""))
