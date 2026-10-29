"""Synthetic laptop catalog (fictional brands, models, shops) in an in-memory SQLite database.

The catalog is generated deterministically from a fixed seed so that screenshots for the paper are
reproducible. Product images are neutral placeholder drawings (see `placeholder_svg`), so that the
interaction paradigm, not the merchandise, is in the foreground.
"""

import random
import sqlite3
import threading

SEED = 27

# name: (price factor, battery factor, weight factor, series names)
BRANDS = {
    "Aero": (1.15, 1.15, 0.95, ["", "Pro", "Air"]),
    "Corvo": (1.30, 0.85, 1.00, ["Slim", "Studio", "Air"]),
    "Kestrel": (0.90, 0.95, 1.10, ["", "X", "Air"]),
    "Lumo": (0.75, 1.05, 1.05, ["Go", "Pro", "Air"]),
    "Nimbus": (1.20, 1.00, 0.88, ["", "Pro", "Air"]),
    "Orbit": (0.80, 0.85, 1.15, ["", "Plus", "Air"]),
    "Tessel": (1.00, 1.05, 1.00, ["Flex", "Pro", "Air"]),
    "Vela": (0.90, 1.10, 1.02, ["Book", "Book Pro", "Air"]),
}
SIZES = {13: 13.3, 14: 14.0, 16: 16.0}
SHOPS = ["Shop A", "Shop B", "Shop C", "Shop D", "Shop E", "Shop F"]

# Attributes that plans may refer to: column, label, unit formatting.
ATTRIBUTES = {
    "price": "price",
    "weight_kg": "weight",
    "battery_h": "battery life",
    "ram_gb": "RAM",
    "storage_gb": "storage",
    "display_in": "display size",
    "display_type": "display panel",
    "brand": "brand",
    "delivery": "delivery",
    "rating": "rating",
    "name": "model",
    "battery_per_100eur": "battery life per euro",
}
DELIVERY_LABELS = {1: "tomorrow", 3: "2-3 days", 7: "within a week"}


def _series_role(series: str) -> str:
    if "Air" in series:
        return "air"
    if "Pro" in series or series in ("X", "Plus", "Studio"):
        return "pro"
    return "base"


def _round_price(value: float) -> int:
    """Shop-style prices such as 949 or 1,299."""
    return int(round(value / 50)) * 50 - 1


def generate():
    rng = random.Random(SEED)
    products, offers = [], []
    for brand, (price_f, battery_f, weight_f, series_list) in BRANDS.items():
        for series in series_list:
            role = _series_role(series)
            for size, display_in in SIZES.items():
                if role == "air" and size == 16:
                    continue
                base_price = {"base": 799, "air": 999, "pro": 1399}[role]
                price = base_price * price_f + {13: -60, 14: 0, 16: 160}[size]
                price = _round_price(price * rng.uniform(0.93, 1.07))
                weight = {13: 1.18, 14: 1.36, 16: 1.92}[size] * {"base": 1.0, "air": 0.86, "pro": 1.08}[role]
                weight = round(weight * weight_f * rng.uniform(0.96, 1.04), 2)
                battery = 13.0 * battery_f * {"base": 1.0, "air": 1.08, "pro": 0.92}[role] * {13: 0.97, 14: 1.0, 16: 1.06}[size]
                battery = round(battery * rng.uniform(0.92, 1.08) * 2) / 2
                ram = 32 if role == "pro" and price > 1500 else 16 if role != "base" or price > 900 else 8
                storage = 1024 if price > 1500 else 512 if price > 850 else 256
                oled = role == "pro" or (role == "air" and rng.random() < 0.5)
                name = " ".join(part for part in (brand, series, str(size)) if part)
                pid = len(products) + 1
                shop_count = rng.randint(2, 5)
                days = []
                for shop in rng.sample(SHOPS, shop_count):
                    shop_price = int(round(price * rng.uniform(0.94, 1.03) / 10)) * 10 - 1
                    day = rng.choice([1, 1, 2, 3, 5, 7])
                    days.append(day)
                    offers.append((pid, shop, shop_price, day))
                fastest = min(days)
                products.append({
                    "id": pid, "name": name, "brand": brand, "series": series, "price": price,
                    "weight_kg": weight, "battery_h": battery, "ram_gb": ram, "storage_gb": storage,
                    "display_in": display_in, "display_type": "OLED" if oled else "IPS",
                    "rating": round(rng.uniform(3.7, 4.8), 1), "reviews": rng.randint(18, 940),
                    "delivery": DELIVERY_LABELS[1 if fastest == 1 else 3 if fastest <= 3 else 7],
                })
    return products, offers


class Catalog:
    def __init__(self):
        self.products, offers = generate()
        self.by_id = {p["id"]: p for p in self.products}
        self.db = sqlite3.connect(":memory:", check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        columns = list(self.products[0])
        self.db.execute(f"CREATE TABLE laptops ({', '.join(columns)})")
        self.db.executemany(
            f"INSERT INTO laptops VALUES ({', '.join('?' * len(columns))})",
            [tuple(p[c] for c in columns) for p in self.products],
        )
        self.db.execute("CREATE TABLE offers (laptop_id, shop, price, delivery_days)")
        self.db.executemany("INSERT INTO offers VALUES (?, ?, ?, ?)", offers)

    def query(self, sql: str, params: list) -> list[dict]:
        with self.lock:
            return [dict(row) for row in self.db.execute(sql, params)]

    def names(self) -> list[str]:
        return [p["name"] for p in self.products]

    def summary(self) -> dict:
        prices = [p["price"] for p in self.products]
        return {
            "laptops": len(self.products),
            "brands": len(BRANDS),
            "shops": len(SHOPS),
            "price_min": min(prices),
            "price_max": max(prices),
        }


def placeholder_svg(product: dict) -> str:
    """Neutral line drawing of a laptop; the lid width reflects the display size."""
    scale = {13.3: 0.82, 14.0: 0.9, 16.0: 1.0}.get(product["display_in"], 0.9)
    width, height = 132 * scale, 82 * scale
    x, y = (160 - width) / 2, 92 - height
    screen = "#e4e4e4" if product["display_type"] == "OLED" else "#efefef"
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 160 110" role="img" aria-label="Placeholder image">
  <rect width="160" height="110" fill="#f8f8f8"/>
  <rect x="{x:.1f}" y="{y:.1f}" width="{width:.1f}" height="{height:.1f}" rx="4" fill="#fff" stroke="#bdbdbd" stroke-width="1.5"/>
  <rect x="{x + 6:.1f}" y="{y + 6:.1f}" width="{width - 12:.1f}" height="{height - 12:.1f}" fill="{screen}"/>
  <path d="M{x - 10:.1f} 92 h{width + 20:.1f} l-6 7 h-{width + 8:.1f} z" fill="#fff" stroke="#bdbdbd" stroke-width="1.5"/>
  <text x="80" y="{y + height / 2 + 4:.1f}" text-anchor="middle" font-family="Verdana, sans-serif" font-size="11" fill="#9a9a9a">{product["display_in"]:g}&#8243;</text>
</svg>"""
