"""Query plans: the structured representation behind every turn.

Typed questions, clicks, and follow-up questions all become a `Plan`. From a plan, the system derives
the SQL query (shown in the "Query" tab), the natural-language interpretation (P3), and the verbalized
user question (P4); see `language.py`.
"""

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from .catalog import DELIVERY_LABELS, Catalog

FILTER_OPS = {
    "price": {"<", "<=", ">", ">="},
    "weight_kg": {"<=", ">="},
    "battery_h": {">="},
    "ram_gb": {"=", ">="},
    "storage_gb": {"=", ">="},
    "display_in": {"="},
    "display_type": {"="},
    "brand": {"="},
    "delivery": {"="},
    "rating": {">="},
    "name": {"="},
}
SORT_ATTRS = {"recommended", "price", "weight_kg", "battery_h", "rating", "battery_per_100eur"}
# Recommendation: the rating, weighted by the number of reviews (Bayesian average with 50 reviews of 4.2).
SORT_COLUMNS = {
    "recommended": "(rating * reviews + 4.2 * 50) / (reviews + 50)",
    "battery_per_100eur": "battery_h * 100.0 / price",
}
METRICS = {
    "battery_per_100eur": ("ROUND(AVG(battery_h * 100.0 / price), 2)", "DESC"),
    "avg_battery": ("ROUND(AVG(battery_h), 1)", "DESC"),
    "avg_price": ("ROUND(AVG(price))", "ASC"),
    "avg_rating": ("ROUND(AVG(rating), 2)", "DESC"),
    "count": ("COUNT(*)", "DESC"),
}
FACETS = ["ram_gb", "display_in", "display_type", "delivery", "brand"]
LIST_LIMIT = 60
GROUP_MEMBERS = 5


class Filter(BaseModel):
    attr: str
    op: str
    value: str | float | int

    @model_validator(mode="after")
    def check(self):
        if self.op not in FILTER_OPS.get(self.attr, set()):
            raise ValueError(f"unsupported filter {self.attr} {self.op}")
        return self


class Sort(BaseModel):
    attr: str
    dir: Literal["asc", "desc"]

    @model_validator(mode="after")
    def check(self):
        if self.attr not in SORT_ATTRS:
            raise ValueError(f"unsupported sort attribute {self.attr}")
        return self


class Plan(BaseModel):
    kind: Literal["list", "group", "count", "offers"]
    filters: list[Filter] = Field(default_factory=list, max_length=12)
    sort: Sort | None = None
    group_by: Literal["brand"] | None = None
    metric: str | None = None
    product_id: int | None = None
    max_price: float | None = None
    ids: list[int] | None = Field(default=None, max_length=60)  # products the user selected

    @model_validator(mode="after")
    def check(self):
        if self.kind == "group" and (self.group_by is None or self.metric not in METRICS):
            raise ValueError("group plans need group_by and a known metric")
        if self.kind == "offers" and self.product_id is None:
            raise ValueError("offers plans need a product_id")
        return self

    def with_filter(self, attr: str, op: str, value) -> "Plan":
        """Copy with a filter added; an existing filter on the same attribute and direction is replaced."""
        same = {"=": {"="}, "<": {"<", "<="}, "<=": {"<", "<="}, ">": {">", ">="}, ">=": {">", ">="}}[op]
        filters = [f for f in self.filters if not (f.attr == attr and (f.op in same or op == "=" or f.op == "="))]
        return self.model_copy(update={"filters": [*filters, Filter(attr=attr, op=op, value=value)]})

    def filter_value(self, attr: str, op: str | None = None):
        for f in self.filters:
            if f.attr == attr and (op is None or f.op == op):
                return f.value
        return None


def _where(plan: Plan) -> tuple[str, list]:
    if not plan.filters and not plan.ids:
        return "", []
    clauses, params = [], []
    if plan.ids:
        clauses.append(f"id IN ({', '.join('?' * len(plan.ids))})")
        params.extend(plan.ids)
    for f in plan.filters:
        clauses.append(f"{f.attr} {f.op} ?")
        params.append(f.value)
    return "WHERE " + "\n  AND ".join(clauses), params


def to_sql(plan: Plan) -> tuple[str, list]:
    where, params = _where(plan)
    if plan.kind == "offers":
        sql = "SELECT shop, price, delivery_days\nFROM offers\nWHERE laptop_id = ?"
        params = [plan.product_id]
        if plan.max_price is not None:
            sql += "\n  AND price <= ?"
            params.append(plan.max_price)
        delivery = plan.filter_value("delivery")
        if delivery is not None:
            # A laptop's delivery is that of its fastest offer; offers meet it by arriving as fast or faster.
            sql += "\n  AND delivery_days <= ?"
            params.append({label: days for days, label in DELIVERY_LABELS.items()}[delivery])
        return sql + "\nORDER BY price ASC, delivery_days ASC", params
    if plan.kind == "count":
        return f"SELECT COUNT(*) AS laptops\nFROM laptops\n{where}".strip(), params
    if plan.kind == "group":
        expression, direction = METRICS[plan.metric]
        sql = (f"SELECT brand, COUNT(*) AS models, ROUND(AVG(price)) AS avg_price,\n"
               f"       ROUND(AVG(battery_h), 1) AS avg_battery, {expression} AS metric\n"
               f"FROM laptops\n{where}\nGROUP BY brand\nORDER BY metric {direction}")
        return sql.replace("\n\n", "\n"), params
    order = ""
    if plan.sort:
        column = SORT_COLUMNS.get(plan.sort.attr, plan.sort.attr)
        order = f"\nORDER BY {column} {plan.sort.dir.upper()}"
    sql = f"SELECT *\nFROM laptops\n{where}{order}\nLIMIT {LIST_LIMIT}"
    return sql.replace("\n\n", "\n"), params


def readable_sql(sql: str, params: list) -> str:
    """SQL with parameters inlined, for display only."""
    for value in params:
        literal = f"'{value}'" if isinstance(value, str) else f"{value:g}" if isinstance(value, float) else str(value)
        sql = sql.replace("?", literal, 1)
    return sql


def facets(catalog: Catalog, plan: Plan) -> list[dict]:
    """Value counts over the filtered laptops, for facets shown inside the answer."""
    where, params = _where(plan)
    result = []
    for attr in FACETS:
        if plan.kind == "group" and attr == plan.group_by:
            continue
        rows = catalog.query(
            f"SELECT {attr} AS value, COUNT(*) AS n FROM laptops {where} GROUP BY {attr} ORDER BY {attr}", params)
        if len(rows) < 2:
            continue
        if attr == "delivery":
            rows.sort(key=lambda r: ["tomorrow", "2-3 days", "within a week"].index(r["value"]))
        result.append({"attr": attr, "values": [{"value": r["value"], "count": r["n"]} for r in rows]})
    return result


def execute(catalog: Catalog, plan: Plan) -> dict:
    sql, params = to_sql(plan)
    rows = catalog.query(sql, params)
    result = {"sql": readable_sql(sql, params), "rows": rows}
    if plan.kind == "list":
        where, wparams = _where(plan)
        result["total"] = catalog.query(f"SELECT COUNT(*) AS n FROM laptops {where}", wparams)[0]["n"]
        result["truncated"] = result["total"] > len(rows)
    elif plan.kind == "group":
        order = {"battery_per_100eur": "battery_h * 100.0 / price DESC", "avg_battery": "battery_h DESC",
                 "avg_price": "price ASC", "avg_rating": "rating DESC", "count": "rating DESC"}[plan.metric]
        where, wparams = _where(plan)
        connector = "AND" if where else "WHERE"
        for row in rows:
            members = catalog.query(
                f"SELECT * FROM laptops {where} {connector} brand = ? ORDER BY {order}", [*wparams, row["brand"]])
            row["members"] = members[:GROUP_MEMBERS]
            row["more"] = max(0, len(members) - GROUP_MEMBERS)
        result["total"] = sum(row["models"] for row in rows)
    elif plan.kind == "offers":
        result["product"] = catalog.by_id.get(plan.product_id)
    if plan.kind in ("list", "group"):
        result["facets"] = facets(catalog, plan)
    return result
