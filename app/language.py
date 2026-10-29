"""Natural language around plans: parsing typed questions, verbalizing plans as user questions (P4),
stating the system's interpretation (P3), and deriving observations and follow-up questions.

Version 1 uses a small rule-based parser, so that the prototype runs offline and screenshots are
reproducible. Verbalization and parsing are kept consistent: a verbalized question, typed back in,
yields the same plan (see tests).
"""

import re

from .catalog import BRANDS, Catalog
from .plan import Plan, Sort

LIGHTWEIGHT = 1.4

# ---------------------------------------------------------------------------------------------------
# Formatting


def euro(value) -> str:
    return f"€{value:,.0f}"


def fmt_display(value) -> str:
    return f"{float(value):g}″"


def fmt_delivery(value: str) -> str:
    return value.replace("-", "–")


def fmt_value(attr: str, value) -> str:
    return {
        "price": lambda v: euro(v),
        "weight_kg": lambda v: f"{v:g} kg",
        "battery_h": lambda v: f"{v:g} h",
        "ram_gb": lambda v: f"{v} GB",
        "storage_gb": lambda v: f"{v} GB" if v < 1000 else "1 TB",
        "display_in": fmt_display,
        "delivery": fmt_delivery,
        "rating": lambda v: f"{v:g}",
    }.get(attr, str)(value)


def delivery_phrase(value) -> str:
    if value == "tomorrow":
        return "available for delivery tomorrow"
    if value == "within a week":
        return "deliverable within a week"
    return f"deliverable in {fmt_delivery(str(value))}"


def join(parts: list[str]) -> str:
    parts = [p for p in parts if p]
    if len(parts) <= 1:
        return "".join(parts)
    return ", ".join(parts[:-1]) + " and " + parts[-1]


# ---------------------------------------------------------------------------------------------------
# Plan -> user question (P4)


def noun_phrase(plan: Plan) -> str:
    """E.g. 'lightweight Lumo 14-inch laptops under €1,000 with 16 GB RAM'."""
    pre, post, with_ = [], [], []
    for f in plan.filters:
        a, op, v = f.attr, f.op, f.value
        if a == "weight_kg" and op == "<=" and v == LIGHTWEIGHT:
            pre.insert(0, "lightweight")
        elif a == "weight_kg":
            post.append(f"weighing {'at most' if op == '<=' else 'at least'} {fmt_value(a, v)}")
        elif a == "brand":
            pre.append(str(v))
        elif a == "display_in":
            pre.append(f"{float(v):g}-inch")
        elif a == "display_type":
            pre.append(str(v))
        elif a == "price":
            post.insert(0, {"<": "under", "<=": "up to", ">": "over", ">=": "from"}[op] + " " + euro(v))
        elif a in ("ram_gb", "storage_gb"):
            unit = "RAM" if a == "ram_gb" else "storage"
            with_.append(f"{'at least ' if op == '>=' else ''}{fmt_value(a, v)} {unit}")
        elif a == "battery_h":
            with_.append(f"at least {fmt_value(a, v)} battery life")
        elif a == "rating":
            post.append(f"rated at least {fmt_value(a, v)}")
        elif a == "delivery":
            post.append(delivery_phrase(v))
    if with_:
        post.append("with " + join(with_))
    if plan.ids:
        pre.insert(0, "selected")
    return " ".join([*pre, "laptops", *post])


LIST_PREDICATES = {
    ("recommended", "desc"): "do you recommend",
    ("battery_h", "desc"): "have the longest battery life",
    ("battery_h", "asc"): "have the shortest battery life",
    ("price", "asc"): "are the cheapest",
    ("price", "desc"): "are the most expensive",
    ("weight_kg", "asc"): "are the lightest",
    ("weight_kg", "desc"): "are the heaviest",
    ("rating", "desc"): "are rated best",
    ("rating", "asc"): "are rated worst",
    ("battery_per_100eur", "desc"): "offer the most battery life per euro",
}


def question(plan: Plan, catalog: Catalog) -> str:
    if plan.kind == "offers":
        product = catalog.by_id[plan.product_id]
        bound = f" for {euro(plan.max_price)} or less" if plan.max_price is not None else ""
        delivery = plan.filter_value("delivery")
        when = f" {delivery_phrase(delivery)}" if delivery is not None else ""
        return f"Which shops offer the {product['name']}{when}{bound}?"
    np = noun_phrase(plan)
    if plan.kind == "count":
        return f"How many {np} are there?"
    if plan.kind == "group":
        return {
            "battery_per_100eur": f"Which brands offer the most battery life per euro among {np}?",
            "avg_battery": f"Which brands have the longest battery life among {np}?",
            "avg_price": f"Which brands offer the cheapest {np} on average?",
            "avg_rating": f"Which brands have the best-rated {np}?",
            "count": f"Which brands offer the most {np}?",
        }[plan.metric]
    name = plan.filter_value("name")
    if name is not None:
        return f"Show me the {name}."
    if plan.sort is None:
        return f"Which {np} are there?"
    return f"Which {np} {LIST_PREDICATES[(plan.sort.attr, plan.sort.dir)]}?"


# ---------------------------------------------------------------------------------------------------
# Plan -> system interpretation (P3)


CLAUSE_ORDER = ["weight_kg", "price", "display_in", "display_type", "ram_gb", "storage_gb", "battery_h", "rating",
                "brand", "delivery", "name"]


def _clauses(plan: Plan) -> list[str]:
    clauses = []
    for f in sorted(plan.filters, key=lambda f: CLAUSE_ORDER.index(f.attr)):
        a, op, v = f.attr, f.op, f.value
        if a == "weight_kg":
            clauses.append(f"weighing {'at most' if op == '<=' else 'at least'} {fmt_value(a, v)}")
        elif a == "price":
            clauses.append("priced " + {"<": "below", "<=": "at most", ">": "above", ">=": "from"}[op] + " " + euro(v))
        elif a == "brand":
            clauses.append(f"from {v}")
        elif a == "display_in":
            panel = plan.filter_value("display_type")
            clauses.append(f"with a {fmt_display(v)} {panel + ' ' if panel else ''}display")
        elif a == "display_type":
            if plan.filter_value("display_in") is None:
                clauses.append(f"with an {v} display" if str(v)[0] in "AEIOU" else f"with a {v} display")
        elif a in ("ram_gb", "storage_gb"):
            unit = "RAM" if a == "ram_gb" else "storage"
            clauses.append(f"with {'at least ' if op == '>=' else ''}{fmt_value(a, v)} {unit}")
        elif a == "battery_h":
            clauses.append(f"with at least {fmt_value(a, v)} battery life")
        elif a == "rating":
            clauses.append(f"rated at least {fmt_value(a, v)}")
        elif a == "delivery":
            clauses.append(delivery_phrase(v))
        elif a == "name":
            clauses.append(f"named {v}")
    return clauses


SORT_PHRASES = {
    "recommended": "recommendation: rating weighted by the number of reviews",
    "battery_h": "battery life", "price": "price", "weight_kg": "weight", "rating": "rating",
    "battery_per_100eur": "battery life per euro",
}
GROUP_PHRASES = {
    "battery_per_100eur": ["compute their battery hours per €100", "average them per brand"],
    "avg_battery": ["average their battery life per brand"],
    "avg_price": ["average their prices per brand"],
    "avg_rating": ["average their ratings per brand"],
    "count": ["count them per brand"],
}


def interpretation(plan: Plan, catalog: Catalog) -> str:
    if plan.kind == "offers":
        product = catalog.by_id[plan.product_id]
        bound = f" at or below {euro(plan.max_price)}" if plan.max_price is not None else ""
        delivery = plan.filter_value("delivery")
        when = f", {delivery_phrase(delivery)}" if delivery is not None else ""
        return f"I'll look up current offers for the {product['name']}{bound}{when}."
    name = plan.filter_value("name")
    if name is not None:
        return f"I'll look up the {name}."
    clauses = _clauses(plan)
    if plan.ids:
        n = len(plan.ids)
        selection = f"the {n} selected laptop{'s' if n > 1 else ''}" + (f" {join(clauses)}" if clauses else "")
    else:
        selection = f"laptops {join(clauses)}" if clauses else "all laptops"
    if plan.kind == "count":
        return f"I'll count {selection}."
    steps = [f"{'take' if plan.ids else 'select'} {selection}"]
    if plan.kind == "group":
        steps.extend(GROUP_PHRASES[plan.metric])
    elif plan.sort:
        first = {"recommended": ("least", "most recommended"), "price": ("cheapest", "most expensive"), "weight_kg": ("lightest", "heaviest"),
                 "battery_h": ("shortest", "longest"), "rating": ("worst", "best"),
                 "battery_per_100eur": ("least", "most")}[plan.sort.attr][plan.sort.dir == "desc"]
        steps.append(f"sort them by {SORT_PHRASES[plan.sort.attr]} ({first} first)")
    text = steps[0] if len(steps) == 1 else ", ".join(steps[:-1]) + ", and " + steps[-1]
    return f"I'll {text}."


# ---------------------------------------------------------------------------------------------------
# Typed question -> plan


NUMBER = r"(\d{1,3}(?:[.,]\d{3})+|\d+(?:\.\d+)?)\s*(k)?"
CURRENCY = r"(?:€|eur\b|euros?\b)"


def _number(text: str, k: str | None) -> float:
    if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", text):
        text = re.sub(r"[.,]", "", text)
    value = float(text)
    return value * 1000 if k else value


class Parsed:
    def __init__(self):
        self.filters: list[tuple[str, str, object]] = []
        self.sort: tuple[str, str] | None = None
        self.kind: str | None = None
        self.metric: str | None = None
        self.product: dict | None = None
        self.subject = False
        self.refinement = False
        self.list_default_sort = False

    def empty(self) -> bool:
        return not (self.filters or self.sort or self.kind or self.product or self.subject)


def parse_text(text: str, catalog: Catalog) -> Parsed:
    t = " " + text.lower().replace("’", "'").replace("″", " inch").replace('"', " inch") + " "
    p = Parsed()

    # Product names (longest match first).
    for name in sorted(catalog.names(), key=len, reverse=True):
        if re.search(rf"\b{re.escape(name.lower())}\b", t):
            p.product = next(x for x in catalog.products if x["name"] == name)
            t = t.replace(name.lower(), " ")
            break

    if re.search(r"\b(shops?|offers?|where (can|do) i (buy|get)|retailers?|stores?)\b", t) and p.product:
        p.kind = "offers"

    # RAM, storage, battery (before prices, as they share number patterns).
    m = re.search(r"(at least|min(?:imum)?|>=?)?\s*(\d+)\s*gb\s*(?:of\s*)?(ram|memory)", t)
    if m:
        p.filters.append(("ram_gb", ">=" if m.group(1) else "=", int(m.group(2))))
        t = t.replace(m.group(0), " ")
    m = re.search(r"(at least|min(?:imum)?)?\s*(\d+)\s*(gb|tb)\s*(?:of\s*)?(storage|ssd|disk)", t)
    if m:
        value = int(m.group(2)) * (1024 if m.group(3) == "tb" else 1)
        p.filters.append(("storage_gb", ">=" if m.group(1) else "=", value))
        t = t.replace(m.group(0), " ")
    m = re.search(r"(?:at least|min(?:imum)?|more than|over)\s*(\d+(?:\.\d+)?)\s*(?:h|hours?)\b(?:\s*(?:of\s*)?battery(?: life)?)?", t)
    if m:
        p.filters.append(("battery_h", ">=", float(m.group(1))))
        t = t.replace(m.group(0), " ")

    # Prices.
    m = re.search(rf"\b(under|below|less than|cheaper than|up to|at most|max(?:imum)?|no more than)\s*{CURRENCY}?\s*{NUMBER}\s*{CURRENCY}?", t)
    if m:
        op = "<" if m.group(1) in ("under", "below", "less than", "cheaper than") else "<="
        p.filters.append(("price", op, _number(m.group(2), m.group(3))))
        t = t.replace(m.group(0), " ")
    m = re.search(rf"{CURRENCY}\s*{NUMBER}\s*{CURRENCY}?\s*or (less|more)", t)
    if m:
        p.filters.append(("price", "<=" if m.group(3) == "less" else ">=", _number(m.group(1), m.group(2))))
        t = t.replace(m.group(0), " ")
    m = re.search(rf"\b(over|above|more than|from|at least)\s*{CURRENCY}?\s*{NUMBER}\s*{CURRENCY}?", t)
    if m and (re.search(CURRENCY, m.group(0)) or _number(m.group(2), m.group(3)) >= 100):
        op = ">" if m.group(1) in ("over", "above", "more than") else ">="
        p.filters.append(("price", op, _number(m.group(2), m.group(3))))
        t = t.replace(m.group(0), " ")

    # Weight, display, panel, delivery, rating, brand.
    m = re.search(r"(?:under|below|at most|up to|less than)\s*(\d+(?:\.\d+)?)\s*kg", t)
    if m:
        p.filters.append(("weight_kg", "<=", float(m.group(1))))
        t = t.replace(m.group(0), " ")
    elif re.search(r"\b(light ?weight|light|portable|ultra ?light)\b", t):
        p.filters.append(("weight_kg", "<=", LIGHTWEIGHT))
    m = re.search(r"\b(13|14|16)(?:\.\d)?\s*(?:-\s*)?(?:inch|in\b|zoll)", t)
    if m:
        p.filters.append(("display_in", "=", {"13": 13.3, "14": 14.0, "16": 16.0}[m.group(1)]))
        t = t.replace(m.group(0), " ")
    if re.search(r"\boled\b", t):
        p.filters.append(("display_type", "=", "OLED"))
    elif re.search(r"\bips\b", t):
        p.filters.append(("display_type", "=", "IPS"))
    if re.search(r"\b(tomorrow|next day|next-day)\b", t):
        p.filters.append(("delivery", "=", "tomorrow"))
    elif re.search(r"\b(2|two)\s*[-–]\s*(3|three) days\b", t):
        p.filters.append(("delivery", "=", "2-3 days"))
    elif re.search(r"\bwithin a week\b", t):
        p.filters.append(("delivery", "=", "within a week"))
    t = re.sub(r"available for delivery|deliverable (in|within)", " ", t)
    m = re.search(r"rated (?:at least |above |over )?(\d(?:\.\d)?)", t)
    if m:
        p.filters.append(("rating", ">=", float(m.group(1))))
        t = t.replace(m.group(0), " ")
    brands = [b for b in BRANDS if re.search(rf"\b{b.lower()}\b", t)]
    group_words = re.search(r"\b(which|what) brands?\b|\b(per|by|each|every) brand\b|\bbrands? (offer|have|make|sell)", t)
    if len(brands) == 1 and not group_words:
        p.filters.append(("brand", "=", brands[0]))

    # Grouping and metrics.
    if group_words:
        p.kind = "group"
        if re.search(r"per (euro|€)|value for money|per price|battery life per|bang for", t):
            p.metric = "battery_per_100eur"
        elif re.search(r"cheap|price|afford|expensive", t):
            p.metric = "avg_price"
        elif re.search(r"rated|rating|review", t):
            p.metric = "avg_rating"
        elif re.search(r"battery", t):
            p.metric = "avg_battery"
        else:
            p.metric = "count"
    elif re.search(r"\bhow many\b|\bnumber of\b", t):
        p.kind = "count"

    # Sorting for lists.
    if p.kind is None:
        p.list_default_sort = True
        for pattern, sort in [
            (r"recommend", ("recommended", "desc")),
            (r"per (euro|€)|value for money|bang for", ("battery_per_100eur", "desc")),
            (r"(longest|most|best|biggest|largest|long) battery|battery life|battery", ("battery_h", "desc")),
            (r"cheapest|lowest price|least expensive|most affordable|cheap", ("price", "asc")),
            (r"most expensive|priciest|highest price", ("price", "desc")),
            (r"lightest|lowest weight", ("weight_kg", "asc")),
            (r"heaviest", ("weight_kg", "desc")),
            (r"best rated|best-rated|highest rated|top rated|rated best|best reviews|most popular|best", ("rating", "desc")),
        ]:
            if re.search(pattern, t):
                p.sort = sort
                break

    p.subject = bool(re.search(r"\b(laptops?|notebooks?|computers?|models?|devices?|brands?)\b", t))
    p.refinement = bool(re.search(r"^\s*(only|just|and|but|what about|how about|with|now|then|of these|among these)\b", t)
                        or re.search(r"\b(these|them|those|ones)\b", t))
    if p.product and p.kind is None and not p.filters and not p.sort:
        p.kind = "list"
        p.filters.append(("name", "=", p.product["name"]))
    return p


WEAK_FILTERS = {"delivery", "weight_kg"}
SELECTION_WORDS = r"\b(these|them|those|which|compare|comparison|differences?|better|best|vs\.?|versus|selected|selection)\b"
OFFER_WORDS = r"\b(shops?|offers?|where (can|do) i (buy|get)|retailers?|stores?)\b"


def parse(text: str, catalog: Catalog, context: Plan | None = None, selection: list[int] | None = None) -> Plan | None:
    """Plan for a typed question, refining the context plan for follow-ups such as 'only with 16 GB RAM'.

    With a selection of products, the question refers only to them: it refines a list of the selection, which
    keeps the delivery condition of the context.
    """
    if selection:
        lowered = text.lower()
        if len(selection) == 1 and re.search(OFFER_WORDS, lowered):
            return Plan(kind="offers", product_id=selection[0])
        # The delivery condition of the previous answer still holds for the selected products.
        delivery = [f for f in context.filters if f.attr == "delivery"] if context else []
        base = Plan(kind="list", ids=selection, filters=delivery, sort=Sort(attr="recommended", dir="desc"))
        plan = parse(text, catalog, base)
        if len(selection) == 1 and (plan is None or (plan.kind == "list" and not plan.filters)):
            # A question about the one attached product, e.g. "How heavy is it?": look it up.
            name = catalog.by_id[selection[0]]["name"]
            plan = Plan(kind="list", filters=[{"attr": "name", "op": "=", "value": name}])
        elif plan is None and re.search(SELECTION_WORDS, lowered):
            plan = base
        if plan is None or plan.kind == "offers":
            return plan
        return Plan.model_validate({**plan.model_dump(), "ids": selection})
    p = parse_text(text, catalog)
    if p.empty():
        return None
    # Without a reference to the catalog, keywords such as "tomorrow" or "best" are not enough (P2).
    anchored = p.subject or p.product or p.kind in ("group", "offers") or any(
        attr not in WEAK_FILTERS for attr, _, _ in p.filters)
    short = len(text.split()) <= 6
    if not anchored and (context is None or not (p.refinement or short)):
        return None
    if p.kind == "offers":
        bound = next((v for a, op, v in p.filters if a == "price" and op in ("<", "<=")), None)
        delivery = [{"attr": a, "op": op, "value": v} for a, op, v in p.filters if a == "delivery"]
        return Plan(kind="offers", product_id=p.product["id"], max_price=bound, filters=delivery)
    refine = context is not None and context.kind in ("list", "group", "count") and (
        p.refinement or (not p.subject and p.kind is None))
    if refine:
        plan = context
        for attr, op, value in p.filters:
            plan = plan.with_filter(attr, op, value)
        if p.kind == "group":
            plan = plan.model_copy(update={"kind": "group", "group_by": "brand", "metric": p.metric, "sort": None})
        elif p.kind == "count":
            plan = plan.model_copy(update={"kind": "count", "sort": None})
        elif p.sort and plan.kind == "list":
            plan = plan.model_copy(update={"sort": Sort(attr=p.sort[0], dir=p.sort[1])})
        return Plan.model_validate(plan.model_dump())
    if p.kind == "group":
        plan = Plan(kind="group", group_by="brand", metric=p.metric)
    else:
        plan = Plan(kind=p.kind or "list")
    for attr, op, value in p.filters:
        plan = plan.with_filter(attr, op, value)
    if plan.kind == "list" and plan.filter_value("name") is None and (p.sort or p.list_default_sort):
        sort = p.sort or ("recommended", "desc")
        plan = plan.model_copy(update={"sort": Sort(attr=sort[0], dir=sort[1])})
    return Plan.model_validate(plan.model_dump())


# ---------------------------------------------------------------------------------------------------
# Observations and follow-up questions


OBSERVATION_PREDICATES = {
    ("recommended", "desc"): ("is recommended most", "rating"),
    ("battery_h", "desc"): ("has the longest battery life", "battery_h"),
    ("battery_h", "asc"): ("has the shortest battery life", "battery_h"),
    ("price", "asc"): ("is the cheapest", "price"),
    ("price", "desc"): ("is the most expensive", "price"),
    ("weight_kg", "asc"): ("is the lightest", "weight_kg"),
    ("weight_kg", "desc"): ("is the heaviest", "weight_kg"),
    ("rating", "desc"): ("is rated best", "rating"),
    ("rating", "asc"): ("is rated worst", "rating"),
    ("battery_per_100eur", "desc"): ("offers the most battery life per euro", "battery_h"),
}
METRIC_PHRASES = {
    "battery_per_100eur": ("offers the most battery life per euro", lambda v: f"{v:.1f} h per €100"),
    "avg_battery": ("has the longest average battery life", lambda v: f"{v:.1f} h"),
    "avg_price": ("is the cheapest on average", lambda v: euro(v)),
    "avg_rating": ("is rated best on average", lambda v: f"{v:.1f}"),
    "count": ("offers the most models", lambda v: f"{v:.0f}"),
}


def observations(plan: Plan, result: dict) -> list[str]:
    rows = result["rows"]
    if plan.kind == "offers":
        if not rows:
            return ["No shop currently offers this laptop within the given price and delivery time."]
        best = rows[0]
        days = "tomorrow" if best["delivery_days"] == 1 else f"in {best['delivery_days']} days"
        return [f"{len(rows)} shop{'s' if len(rows) > 1 else ''} offer{'' if len(rows) > 1 else 's'} it; "
                f"the cheapest offer is from {best['shop']} ({euro(best['price'])}, delivery {days})."]
    if plan.kind == "count":
        return []
    if not rows:
        return ["No laptop matches all conditions."]
    if plan.kind == "group":
        top = rows[0]
        phrase, fmt = METRIC_PHRASES[plan.metric]
        texts = [f"Among {result['total']} matching laptops, {top['brand']} {phrase} ({fmt(top['metric'])})."]
        longest = max(rows, key=lambda r: r["avg_battery"])
        if plan.metric != "avg_battery" and longest["brand"] != top["brand"]:
            texts.append(f"{longest['brand']} has the longest average battery life ({longest['avg_battery']:.1f} h) "
                         f"at {euro(longest['avg_price'])} on average.")
        return texts
    if plan.filter_value("name") is not None:
        p = rows[0]
        return [f"The {p['name']} weighs {fmt_value('weight_kg', p['weight_kg'])}, runs {fmt_value('battery_h', p['battery_h'])} "
                f"on battery, and costs {euro(p['price'])}."]
    top = rows[0]
    texts = []
    if plan.sort:
        phrase, attr = OBSERVATION_PREDICATES[(plan.sort.attr, plan.sort.dir)]
        texts.append(f"Of {result['total']} matching laptop{'s' if result['total'] > 1 else ''}, "
                     f"the {top['name']} {phrase} ({fmt_value(attr, top[attr])}).")
    contrast = ("price", min) if not plan.sort or plan.sort.attr != "price" else ("battery_h", max)
    other = contrast[1](rows, key=lambda r: r[contrast[0]])
    if other["id"] != top["id"]:
        label = "cheapest" if contrast[0] == "price" else "one with the longest battery life"
        texts.append(f"The {label} is the {other['name']} ({fmt_value(contrast[0], other[contrast[0]])}).")
    return texts


def followups(plan: Plan, result: dict, catalog: Catalog) -> list[Plan]:
    rows, plans = result["rows"], []
    if plan.kind == "offers":
        product = catalog.by_id[plan.product_id]
        plans.append(Plan(kind="list", filters=[{"attr": "brand", "op": "=", "value": product["brand"]}],
                          sort={"attr": "battery_h", "dir": "desc"}))
        return plans
    if not rows or plan.kind == "count":
        if plan.filters:
            plans.append(plan.model_copy(update={"filters": plan.filters[:-1]}))
        return plans
    if plan.kind == "group":
        sort = {"battery_per_100eur": ("battery_per_100eur", "desc"), "avg_battery": ("battery_h", "desc"),
                "avg_price": ("price", "asc"), "avg_rating": ("rating", "desc"), "count": ("rating", "desc")}[plan.metric]
        plans.append(Plan(kind="list", filters=[*plan.filters, {"attr": "brand", "op": "=", "value": rows[0]["brand"]}],
                          sort={"attr": sort[0], "dir": sort[1]}, ids=plan.ids))
        if plan.filter_value("display_type") is None:
            plans.append(plan.with_filter("display_type", "=", "OLED"))
        return plans
    delivery = [f for f in plan.filters if f.attr == "delivery"]  # offers keep the delivery condition
    if plan.filter_value("name") is not None:
        return [Plan(kind="offers", product_id=rows[0]["id"], filters=delivery)]
    plans.append(Plan(kind="offers", product_id=rows[0]["id"], filters=delivery))
    if result["total"] > 3 and plan.filter_value("brand") is None:
        metric = "battery_per_100eur" if plan.sort and plan.sort.attr in ("battery_h", "battery_per_100eur") else \
            "avg_price" if plan.sort and plan.sort.attr == "price" else "avg_rating"
        plans.append(Plan(kind="group", filters=plan.filters, group_by="brand", metric=metric, ids=plan.ids))
    if plan.filter_value("delivery") is None and any(r["delivery"] == "tomorrow" for r in rows):
        plans.append(plan.with_filter("delivery", "=", "tomorrow"))
    return plans[:3]


# Suggested questions, most common shopping needs first (budget, mobility, minimum specs), then an
# aggregation that facets cannot express (P1).
EXAMPLES = [
    "Which laptops under €1,000 do you recommend?",
    "Which lightweight laptops have the longest battery life?",
    "Which laptops with 16 GB RAM are the cheapest?",
    "Which brands offer the most battery life per euro among lightweight laptops?",
]
