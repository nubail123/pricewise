"""Conservative cross-store matching. Titles alone are never 'verified'."""
from __future__ import annotations

import hashlib
import re
import unicodedata
from difflib import SequenceMatcher
from functools import lru_cache

from store_config import STORE_IDS

STOP_WORDS = set("a an and the with for of to in by on wireless bluetooth new latest original genuine premium compatible quality design noise cancelling canceling headphones headphone earbuds earphones earphone over ear audio battery hours hour playtime black white silver blue green red pink gold gray grey midnight starlight titanium international version model edition warranty uae middle east".split())
COLORS = {"black", "white", "silver", "blue", "green", "red", "pink", "gold", "gray", "grey", "purple", "midnight", "starlight", "titanium", "beige", "orange", "yellow", "cream", "teal", "ultramarine", "navy", "graphite", "lavender", "desert", "natural", "violet", "icyblue", "graygreen", "charcoal", "lilac", "mint", "cobalt", "sage", "cyan", "magenta", "coral", "bronze", "brown", "rose", "sand", "denim", "indigo", "amber", "aqua", "plum", "maroon", "burgundy", "turquoise", "olive", "citrus", "frost", "pistachio"}
COLOR_ALIASES = {"grey": "gray", "blk": "black", "wht": "white", "slv": "silver", "blu": "blue", "grn": "green", "pnk": "pink", "gld": "gold", "gry": "gray", "prp": "purple"}
ACCESSORY = re.compile(r"\b(case|cover|protector|earpads?|replacement|strap|cable|adapter|screen guard|charger|charging station|dock|controller|dualsense|joy-?con|headset|portal|camera|remote|stand|mount|holder|grip|skin|shell|pouch|bag|sleeve|filter|bin|nozzle|attachment|brush|head|spare|part|gift card|wallet|subscription|disc drive)\b", re.I)


@lru_cache(maxsize=4096)
def normal(text):
    text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode().lower()
    text = re.sub(r"\b(icy|sky|deep|dark|light|pacific|midnight|cosmic|mystic|awesome)\s+blue\b", lambda m: m.group(1) + "blue" if m.group(1) == "icy" else "blue", text)
    text = re.sub(r"\b(?:gray|grey)\s*green\b", "graygreen", text)
    return re.sub(r"[^a-z0-9\s]", " ", text)


@lru_cache(maxsize=4096)
def tokens(text):
    # Compact model IDs make WH-1000XM5 and WH1000XM5 comparable.
    return (set(normal(text).split()) - STOP_WORDS) | models(text)


@lru_cache(maxsize=4096)
def models(title):
    text = normal(title)
    found = set()
    patterns = [
        r"\biphone\s*(\d{1,2})\s*(pro\s*max|pro|plus|mini|air|e)?\b",
        r"\bgalaxy\s*(s\s*\d{1,2}|a\s*\d{1,2}|m\s*\d{1,2}|z\s*(?:fold|flip)\s*\d)\s*(ultra|plus|fe)?\b",
        r"\bgalaxy\s*watch\s*(\d|ultra|fe)\s*(classic|pro)?\b",
        r"\bapple\s*watch\s*(series\s*\d{1,2}|ultra\s*\d?|se\s*\d?)\b",
        r"\bipad\s*(pro|air|mini)?\s*(?:m\s*\d|\d{1,2})?\b",
    ]
    # Canonical AirPods generations, including "Pro (2nd generation)".
    airpods = re.search(r"\bair\s*pods?\s*(pro|max)?\b", text)
    if airpods:
        tail = text[airpods.end():airpods.end() + 65]
        generation = re.search(r"^\s*(\d)\b|\b(\d)(?:st|nd|rd|th)?\s*(?:generation|gen)\b|\b(?:generation|gen)\s*(\d)\b", tail)
        number = next((v for v in generation.groups() if v), "") if generation else ""
        found.add("airpods" + (airpods.group(1) or "") + number)
    macbook = re.search(r"\bmacbook\s*(air|pro|neo)\b", text)
    chip = re.search(r"\b(m\s*\d\s*(?:pro|max|ultra)?|a\d{2}\s*pro)\b", text)
    if macbook:
        found.add("macbook" + macbook.group(1) + (re.sub(r"\s+", "", chip.group(1)) if chip else ""))
    ps = re.search(r"\b(?:playstation|ps)\s*(\d)\b", text)
    if ps:
        ps_sub = "pro" if re.search(r"\bpro\b", text) else "slim" if re.search(r"\bslim\b", text) else ""
        found.add("playstation" + ps.group(1) + ps_sub)
    if re.search(r"\bdyson\b", text):
        dyson_gen = re.search(r"\b(v\s*\d{1,2}s?|gen\s*5)\b", text)
        if dyson_gen:
            base_gen = re.sub(r"\s+", "", dyson_gen.group(1))
            dyson_sub = next((tag for pattern, tag in (
                (r"\bsubmarine\b", "submarine"),
                (r"\btotal\s*clean\b", "totalclean"),
                (r"\babsolute\b", "absolute"),
                (r"\bextra\b", "extra"),
                (r"\bfluffy\b", "fluffy"),
                (r"\borigin\b", "origin"),
                (r"\bdetect\b", "detect"),
            ) if re.search(pattern, text)), "")
            if dyson_sub == "submarine" and base_gen.startswith("v15"):
                base_gen = "v15s"
            found.add("dyson" + base_gen + dyson_sub)
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            value = re.sub(r"\s+", "", match.group(0))
            found.add(value)
    for match in re.finditer(r"\b(?:core\s*ultra\s*\d\s*\d{3}[a-z]{0,2}|core\s*i[3579]\s*\d{4,5}[a-z]{0,2}|core\s*[3579]\s*\d{3}[a-z]{0,2}|ryzen\s*[3579]\s*\d{4}[a-z]{0,2}|snapdragon\s*x\s*(?:elite|plus))\b", text):
        found.add("cpu" + re.sub(r"\s+", "", match.group(0)))
    for match in re.finditer(r"\b(?=[a-z0-9/-]*[a-z])(?=[a-z0-9/-]*\d)[a-z]{1,6}[- ]?\d{2,5}[a-z0-9]*(?:[-/][a-z0-9]{1,8})?\b", str(title).lower()):
        raw = match.group(0)
        if "/" in raw:
            left, right = raw.split("/", 1)
            model = re.sub(r"[^a-z0-9]", "", left) + ("/" + re.sub(r"[^a-z0-9]", "", right) if any(ch.isdigit() for ch in right) and len(re.sub(r"[^a-z0-9]", "", left)) >= 4 else "")
        else:
            model = re.sub(r"[^a-z0-9]", "", raw)
        model = re.sub(r"^nc(?=[a-z]{2,4}\d{2,5})", "", model)
        if re.search(r"\b(?:iphone|ipad)\b", text) and re.fullmatch(r"a1[4-9](?:pro)?", model):
            continue
        if not re.search(r"^(?:\d+(?:gb|tb|mah|hz|inch|in|hour|hrs|mm|cm|kg|g|ml|l|w|v)|(?:19|20)\d{2}|ddr\d|wifi\d|bt\d|usb\d|gen\d|cat\d|ip\d{2}|5g|4g|ios\d{1,2}|ipados\d{1,2}|macos\d{1,2})$", model) and not re.search(r"(?:gb|tb|mah|hz|inch|hour|hrs|mm|watts?)$", model):
            found.add(model)
    return found


def is_accessory(title):
    text = str(title)
    # Earbuds/headphones sold WITH a charging/carrying case, or consoles sold WITH a controller, are core products.
    cleaned = re.sub(r"\b(?:with|including|includes|plus|\+)\s+(?:extra\s+|additional\s+|dual\s+)?(?:[a-z0-9-]+\s+){0,6}(?:case|controller|dualsense|cable|adapter|strap|charger)\b", "", text, flags=re.I)
    if re.search(r"\b(?:marvel'?s?\s+wolverine|spider[- ]?man\s*\d?|god\s+of\s+war|gran\s+turismo|horizon|astro\s+bot|call\s+of\s+duty|fc\s*2\d|fifa|gta|assassin'?s\s+creed|ghost\s+of\s+yotei|final\s+fantasy|elden\s+ring|resident\s+evil|tekken|street\s+fighter|game\s+disc|video\s+game|ps5\s+game)\b", cleaned, re.I) and not re.search(r"\b(?:edition\s+console|console\s+bundle|slim\s+console|digital\s+console|disc\s+console)\b", cleaned, re.I):
        return True
    if re.search(r"\b(console|smartphone|mobile phone|laptop|notebook|macbook|ipad|tablet|smartwatch|air fryer|vacuum|television|monitor)\b", cleaned, re.I) and not re.search(r"\b(for|compatible with|fits|replacement|protector|cover|case|skin|bag|pouch|stand|mount|dock|holder|adapter|cable|charger|filter|bin|attachment|spare)\b", cleaned, re.I):
        return False
    if re.search(r"\b(playstation\s*5|ps5|xbox)\b", cleaned, re.I) and not re.search(r"\b(console|digital edition|disc edition|slim)\b", cleaned, re.I):
        return True
    return bool(ACCESSORY.search(cleaned))


@lru_cache(maxsize=4096)
def variants(title):
    text = normal(title)
    words = {COLOR_ALIASES.get(word, word) for word in text.split()}
    capacities = {number + unit for number, unit in re.findall(r"\b(\d+)\s*(gb|tb)\b", text)}
    sizes = {re.sub(r"\s+", "", number) for number in re.findall(r"\b(\d+(?:\s\d+)?)\s*(?:mm|inch|inches)\b", text)}
    colors = words & COLORS
    region = "international" if re.search(r"\b(international|global)\b", text) else "uae" if re.search(r"\b(uae|middle east|mea|tdra|gcc)\b", text) else "ksa" if re.search(r"\b(ksa|saudi)\b", text) else "us" if re.search(r"\b(us|usa|american)\s+(?:version|model|spec|specs)\b", text) else "eu" if re.search(r"\b(eu|european|uk)\s+(?:version|model|spec|specs)\b", text) else "jp" if re.search(r"\b(japan|japanese)\s+(?:version|model|spec|specs)\b", text) else "hk" if re.search(r"\b(hong kong|hk)\s+(?:version|model|spec|specs)\b", text) else None
    condition = "refurbished" if re.search(r"\b(renewed|refurbished|used|pre owned|preowned|pre loved|preloved|second hand|open box|ex display|reconditioned|like new)\b", text) else "unspecified"
    bundle = bool(re.search(r"\b(?:pack of|\d\s*pack|set of|bundle|kit|combo|with extra|extra controller|extra dualsense|2 controllers|dual controller)\b", text) or re.search(r"\s\+\s", str(title)))
    pack_match = re.search(r"\b(?:pack of\s*(\d+)|(\d+)\s*(?:pack|pcs|pieces)|set of\s*(\d+))\b", text)
    pack = ("pack-" + next(v for v in pack_match.groups() if v)) if pack_match else ("bundle" if bundle else None)
    connector = "usb-c" if re.search(r"\b(?:usb|type)\s*c\b", text) else "lightning" if "lightning" in words else None
    watch_network = None
    if re.search(r"\b(?:watch\s*\d*|smartwatch)\b", text):
        watch_network = "lte" if re.search(r"\b(?:lte|cellular|4g|5g)\b", text) else "bluetooth" if re.search(r"\b(?:bluetooth|gps|wifi|wi fi)\b", text) else None
    quantities = set()
    for match in re.finditer(r"\b(\d+(?:\.\d+)?)(\s*)(kg|g|grams?|ml|l|litres?|liters?|ltr)\b", str(title).lower()):
        number, sep, unit = match.groups()
        if unit == "g" and not sep and number in {"2", "3", "4", "5"}:
            continue  # 4G/5G cellular generation, not grams.
        scale = 1000 if unit in {"kg", "l", "ltr", "litre", "liter", "litres", "liters"} else 1
        dimension = "mass" if unit in {"kg", "g", "gram", "grams"} else "volume"
        quantities.add((dimension, round(float(number) * scale, 3)))
    drive = None
    if re.search(r"\b(?:playstation|ps5|xbox)\b", text):
        drive = "digital" if "digital" in words else "disc" if re.search(r"\b(?:disc|disk|standard|cd)\b", text) or not is_accessory(title) else None
    gen = re.search(r"\b(?:(\d{1,2})(?:st|nd|rd|th)\s*gen(?:eration)?|gen(?:eration)?\s*(\d{1,2}))\b", text)
    generation = (gen.group(1) or gen.group(2)) if gen and not re.search(r"\b(?:intel|core|ryzen)\b", text) else None
    return {"capacity": capacities, "size": sizes, "color": colors, "region": region, "condition": condition, "pack": pack, "connector": connector, "watch_network": watch_network, "quantity": quantities, "drive": drive, "generation": generation}


def canonical_barcode(value):
    value = str(value or "").strip()
    if not value.isdigit() or len(value) not in {8, 12, 13, 14} or len(set(value)) == 1:
        return None
    total = sum(int(digit) * (3 if i % 2 == 0 else 1) for i, digit in enumerate(reversed(value[:-1])))
    if (10 - total % 10) % 10 != int(value[-1]):
        return None
    return value.zfill(14)


def match_score(left, right):
    a, b = left["title"], right["title"]
    va, vb = variants(a), variants(b)
    # Reject known differences instead of advertising false savings.
    for key in ("capacity", "size", "color", "quantity"):
        if va[key] and vb[key] and va[key] != vb[key]:
            return 0, "different variants"
    for key in ("connector", "watch_network", "drive", "generation"):
        if va[key] and vb[key] and va[key] != vb[key]:
            return 0, "different connectivity or generation variants"
    if va["condition"] != vb["condition"]:
        return 0, "different condition"
    if va["region"] and vb["region"] and va["region"] != vb["region"]:
        return 0, "different regional versions"
    if va["pack"] != vb["pack"]:
        return 0, "different pack or bundle"
    if is_accessory(a) != is_accessory(b):
        return 0, "accessory versus product"
    if left.get("brand") and right.get("brand") and normal(left["brand"]) != normal(right["brand"]):
        return 0, "different brands"
    if left.get("unit") and right.get("unit") and left["unit"] != right["unit"]:
        return 0, "different pricing units"
    if category(a) != "Other" and category(b) != "Other" and category(a) != category(b):
        return 0, "different product categories"
    ma, mb = models(a), models(b)
    prefixes = ("iphone", "galaxy", "applewatch", "airpods", "macbook", "ipad", "playstation", "dyson", "cpu")
    for prefix in prefixes:
        fa, fb = {m for m in ma if m.startswith(prefix)}, {m for m in mb if m.startswith(prefix)}
        if fa and fb and fa != fb:
            return 0, "different model families or generations"
    specific_a = {m for m in ma if not m.startswith(prefixes) and not re.fullmatch(r"sv\d{2}", m)}
    specific_b = {m for m in mb if not m.startswith(prefixes) and not re.fullmatch(r"sv\d{2}", m)}
    if specific_a and specific_b and not specific_a.intersection(specific_b):
        return 0, "different model identifiers"
    if ma and mb and not ma.intersection(mb):
        return 0, "different model identifiers"
    barcode_a, barcode_b = canonical_barcode(left.get("barcode")), canonical_barcode(right.get("barcode"))
    if barcode_a and barcode_b:
        if barcode_a == barcode_b:
            return 1, "shared product barcode"
        return 0, "different product barcodes"
    ta, tb = tokens(a), tokens(b)
    overlap = len(ta & tb) / max(1, min(len(ta), len(tb)))
    sequence = SequenceMatcher(None, normal(a), normal(b)).ratio()
    if ma & mb and overlap >= 0.55:
        # Marketing-copy overlap is not evidence that a more expensive listing
        # matches better. Use shared identity/variant fields, then price as a tie-break.
        known = sum(bool(va[key]) and va[key] == vb[key] for key in ("capacity", "size", "color", "region", "connector", "watch_network", "drive", "generation"))
        return min(0.96, 0.90 + known * 0.01), "shared model; title-based match"
    if overlap >= 0.8 and sequence >= 0.73 and len(ta & tb) >= 3:
        return 0.73, "similar product titles"
    return 0, "not enough matching product information"


def relevance(title, query):
    tq, tt = tokens(query), tokens(title)
    score = len(tq & tt) / max(len(tq), 1)
    mq, mt = models(query), models(title)
    if mq and mt:
        score += 1.5 if mq == mt else 0.8 if mq & mt else -0.9
    if is_accessory(title) and not is_accessory(query):
        score -= 1.2
    return score


def category(title):
    text = normal(title)
    if re.search(r"\b(watch\s*\d*|smartwatch|fitness tracker|garmin|whoop|fitbit)\b", text):
        return "Wearables"
    if re.search(r"\b(airpods|headphones|earbuds|earphones|headphone|earbud|speaker|soundbar)\b", text):
        return "Audio"
    if re.search(r"\b(playstation|ps5|xbox|nintendo|switch|dualsense|gaming|console)\b", text):
        return "Gaming"
    if re.search(r"\b(laptop|macbook|notebook|monitor|ipad|tablet|imac|pc|desktop)\b", text):
        return "Computing"
    if re.search(r"\b(iphone|galaxy|smartphone|phone|pixel|honor|xiaomi|redmi|oppo|vivo|nothing phone|oneplus|motorola)\b", text):
        return "Phones"
    if re.search(r"\b(dyson|vacuum|fryer|airfryer|blender|coffee|espresso|kettle|microwave|toaster|iron|purifier|humidifier)\b", text):
        return "Home"
    return "Other"


def product_from_group(members, query, scores, reason="Only one store price could be found.", store_ids=STORE_IDS):
    first = members[0]
    offers = {store: next((item for item in members if item["store"] == store), None) for store in store_ids}
    identity = first["store"] + "-" + first["id"]
    count = len(members)
    score = min(scores) if scores else 0
    level = "verified" if scores and all(s == 1 for s in scores) else "likely" if count > 1 else "single"
    eligible = [item for item in members if item.get("available") is True]
    minimum = min((item["price"] for item in eligible), default=None)
    maximum = max((item["price"] for item in eligible), default=None)
    difference = round(maximum - minimum, 2) if len(eligible) >= 2 else None
    lowest = [item["store"] for item in eligible if item["price"] == minimum]
    lower = lowest[0] if difference and lowest else None
    return {
        "id": hashlib.sha256(identity.encode()).hexdigest()[:16],
        "title": first["title"], "brand": first.get("brand") or first["title"].split()[0],
        "image": next((item.get("image") for item in members if item.get("image") and not str(item.get("image")).startswith("https://pimcdn.sharafdg.com")), next((item.get("image") for item in members if item.get("image")), None)),
        "rating": first.get("rating"), "ratingCount": first.get("ratingCount"), "ratingSource": first["store"],
        "category": category(first["title"]), "specs": first.get("specs") or {}, "offers": offers,
        "match": {"level": level, "score": round(score, 2), "reason": "Every cross-store pair shares a product barcode." if level == "verified" else "Model/title matches; every known cross-store variant was checked." if count > 1 else reason},
        "priceDifference": difference, "lowerStore": lower, "lowestStores": lowest if len(eligible) >= 2 else [],
        "offerCount": count, "availableOfferCount": len(eligible), "storeCount": len(store_ids),
        "priceRange": {"min": minimum, "max": maximum},
        "checkedAt": min(item["checkedAt"] for item in members), "searchTerm": query,
        "relevance": round(relevance(first["title"], query), 3),
    }


def group_catalog(items_by_store, query):
    store_ids = tuple(items_by_store)
    groups = []
    for store, rows in items_by_store.items():
        rows = sorted(rows, key=lambda item: (-relevance(item["title"], query), item.get("available") is not True, item["price"]))
        for item in rows:
            candidates = []
            for i, group in enumerate(groups):
                if any(member["store"] == store for member in group["members"]):
                    continue
                checks = [match_score(member, item) for member in group["members"]]
                # No transitive/wildcard merging: EVERY pair must be compatible.
                if checks and all(score >= .7 for score, _ in checks):
                    candidates.append((min(score for score, _ in checks), len(group["members"]), -i, i, checks))
            if candidates:
                _, _, _, i, checks = max(candidates)
                groups[i]["members"].append(item)
                groups[i]["scores"].extend(score for score, _ in checks)
            else:
                groups.append({"members": [item], "scores": []})
    products = [product_from_group(group["members"], query, group["scores"], store_ids=store_ids) for group in groups]
    return sorted(products, key=lambda p: (p["relevance"], p["availableOfferCount"] > 1, p["offerCount"] > 1, p["offerCount"]), reverse=True)


def make_product(noon, jumbo, query, score=0, reason="Only one store price could be found."):
    return product_from_group([item for item in (noon, jumbo) if item], query, [score] if noon and jumbo else [], reason, ("noon", "jumbo"))


def group_products(noon_items, jumbo_items, query):
    # Backward-compatible two-store helper used by adapter/matching unit tests.
    return group_catalog({"noon": noon_items, "jumbo": jumbo_items}, query)
