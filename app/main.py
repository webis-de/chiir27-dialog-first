"""Dialog-First product search: FastAPI backend.

Every turn is answered from a query plan (`plan.py`). Typed questions are parsed into plans; clicks and
follow-up questions arrive as plans and are verbalized as user questions (`language.py`).

Run locally:  uvicorn app.main:app --reload
"""

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import language as lang
from .catalog import Catalog, placeholder_svg
from .plan import Plan, execute

BASE_DIR = Path(__file__).resolve().parent.parent

catalog = Catalog()
app = FastAPI(title="Dialog-First product search", docs_url=None, redoc_url=None, openapi_url=None)


class AskIn(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    context: Plan | None = None
    selection: list[int] = Field(default_factory=list, max_length=60)


class QueryIn(BaseModel):
    plan: Plan


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


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/api/start")
def start():
    """Opening of the dialog: all laptops as a first answer, most recommended first, with facets, a summary of
    the catalog, and example questions instead of follow-ups (P2)."""
    s = catalog.summary()
    welcome = (f"Welcome! The catalog has {s['laptops']} laptops from {s['brands']} brands, offered by {s['shops']} shops "
               f"for {lang.euro(s['price_min'])}–{lang.euro(s['price_max'])[1:]}. Here they are, most recommended first. "
               f"Ask me about them, or narrow them down with the facets.")
    opening = answer(Plan(kind="list", sort={"attr": "recommended", "dir": "desc"}))
    return {**opening, "interpretation": welcome, "observations": [], "followups": [], "examples": lang.EXAMPLES}


@app.post("/api/ask")
def ask(body: AskIn):
    selection = [i for i in body.selection if i in catalog.by_id]
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


@app.post("/api/query")
def query(body: QueryIn):
    """Clicks and follow-up questions: the plan is verbalized as the user's question (P4)."""
    if body.plan.kind == "offers" and body.plan.product_id not in catalog.by_id:
        raise HTTPException(404, "Unknown product")
    return {"question": lang.question(body.plan, catalog), "answer": answer(body.plan)}


@app.post("/api/verbalize")
def verbalize(body: QueryIn):
    """Question for a plan without answering it, e.g. as a preview on hover."""
    return {"question": lang.question(body.plan, catalog)}


@app.get("/api/product/{product_id}")
def product(product_id: int):
    """Product page: details and shop offers. Opening it is a view change, not a turn."""
    if product_id not in catalog.by_id:
        raise HTTPException(404, "Unknown product")
    offers = catalog.query("SELECT shop, price, delivery_days FROM offers WHERE laptop_id = ? "
                           "ORDER BY price ASC, delivery_days ASC", [product_id])
    return {"product": catalog.by_id[product_id], "offers": offers}


@app.get("/img/{product_id}.svg")
def image(product_id: int):
    product = catalog.by_id.get(product_id)
    if product is None:
        raise HTTPException(404, "Unknown product")
    return Response(placeholder_svg(product), media_type="image/svg+xml",
                    headers={"Cache-Control": "public, max-age=86400"})


app.mount("/", StaticFiles(directory=BASE_DIR / "static", html=True), name="static")
