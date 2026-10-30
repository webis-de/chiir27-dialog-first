"""Dialog-First product search: the answers behind the API, independent of the web framework.

Every turn is answered from a query plan (`plan.py`). Typed questions are parsed into plans; clicks and
follow-up questions arrive as plans and are verbalized as user questions (`language.py`).

The same functions serve the FastAPI backend (`main.py`) and the static deployment, in which they run in
the browser with Pyodide (`handle`, called from `static/backend.js`).
"""

import json

from pydantic import BaseModel, Field

from . import language as lang
from .catalog import Catalog
from .plan import Plan, execute

catalog = Catalog()


class AskIn(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    context: Plan | None = None
    selection: list[int] = Field(default_factory=list, max_length=60)


class QueryIn(BaseModel):
    plan: Plan


class UnknownProduct(LookupError):
    pass


def answer(plan: Plan) -> dict:
    result = execute(catalog, plan)
    return {
        "kind": plan.kind,
        "plan": plan.model_dump(),
        "interpretation": lang.interpretation(plan, catalog),
        **result,
        "observations": lang.observations(plan, result),
        "followups": [{"question": lang.question(p, catalog), "plan": p.model_dump()}
                      for p in lang.followups(plan, result, catalog)],
        "facets": [
            {**facet, "values": [
                {**value, "plan": plan.with_filter(facet["attr"], "=", value["value"]).model_dump()}
                for value in facet["values"]]}
            for facet in result.get("facets", [])
        ],
    }


def clarify(term: str, readings: list[lang.Reading]) -> dict:
    """A vague question: answered with its most likely reading if that is likely enough, which the answer
    states, with the other readings as follow-ups; otherwise the readings are offered as candidates, each an
    executable plan verbalized as an unambiguous question (P3)."""
    top = readings[0]
    if top.weight >= lang.CONFIDENT:
        a = answer(top.plan)
        others = [{"question": lang.question(r.plan, catalog), "plan": r.plan.model_dump()} for r in readings[1:]]
        return {**a, "interpretation": f"I read “{term}” as {top.label}. {a['interpretation']}",
                "followups": (others + a["followups"])[:3]}
    candidates = []
    for r in readings:
        result = execute(catalog, r.plan)
        candidates.append({"question": lang.question(r.plan, catalog), "plan": r.plan.model_dump(),
                           "interpretation": lang.interpretation(r.plan, catalog), "sql": result["sql"],
                           "total": result["total"] if r.plan.kind == "list" else len(result["rows"]),
                           "kind": r.plan.kind})
    return {"kind": "clarify", "term": term, "candidates": candidates,
            "interpretation": f"“{term[0].upper() + term[1:]}” can mean several things. Which do you mean?"}


def start() -> dict:
    """Opening of the dialog: all laptops as a first answer, most recommended first, with facets, a summary of
    the catalog, and example questions instead of follow-ups (P2)."""
    s = catalog.summary()
    welcome = (f"Welcome! The catalog has {s['laptops']} laptops from {s['brands']} brands, offered by {s['shops']} shops "
               f"for {lang.euro(s['price_min'])}–{lang.euro(s['price_max'])[1:]}. Here they are, most recommended first. "
               f"Ask me about them, or narrow them down with the facets.")
    opening = answer(Plan(kind="list", sort={"attr": "recommended", "dir": "desc"}))
    return {**opening, "interpretation": welcome, "observations": [], "followups": [], "examples": lang.EXAMPLES}


def ask(body: AskIn) -> dict:
    selection = [i for i in body.selection if i in catalog.by_id]
    vague = lang.readings(body.text, catalog, body.context, selection)
    if vague:
        return clarify(*vague)
    plan = lang.parse(body.text, catalog, body.context, selection)
    if plan is None:
        return {
            "kind": "unanswerable",
            "interpretation": "I can't answer this from the catalog. I can find laptops by price, weight, battery "
                              "life, RAM, storage, display, brand, rating, and delivery, compare brands, and look "
                              "up shop offers, for example:",
            "examples": lang.EXAMPLES,
        }
    return answer(plan)


def query(body: QueryIn) -> dict:
    """Clicks and follow-up questions: the plan is verbalized as the user's question (P4)."""
    if body.plan.kind == "offers" and body.plan.product_id not in catalog.by_id:
        raise UnknownProduct(body.plan.product_id)
    return {"question": lang.question(body.plan, catalog), "answer": answer(body.plan)}


def verbalize(body: QueryIn) -> dict:
    """Question for a plan without answering it, e.g. as a preview on hover."""
    return {"question": lang.question(body.plan, catalog)}


def product(product_id: int) -> dict:
    """Product page: details and shop offers. Opening it is a view change, not a turn."""
    if product_id not in catalog.by_id:
        raise UnknownProduct(product_id)
    offers = catalog.query("SELECT shop, price, delivery_days FROM offers WHERE laptop_id = ? "
                           "ORDER BY price ASC, delivery_days ASC", [product_id])
    return {"product": catalog.by_id[product_id], "offers": offers}


def handle(path: str, body: str | None = None) -> str:
    """The API for the static deployment: request path and JSON body in, JSON answer out."""
    data = json.loads(body) if body else None
    if path == "/api/start":
        result = start()
    elif path == "/api/ask":
        result = ask(AskIn.model_validate(data))
    elif path == "/api/query":
        result = query(QueryIn.model_validate(data))
    elif path == "/api/verbalize":
        result = verbalize(QueryIn.model_validate(data))
    elif path.startswith("/api/product/"):
        result = product(int(path.rsplit("/", 1)[1]))
    else:
        raise LookupError(path)
    return json.dumps(result)
