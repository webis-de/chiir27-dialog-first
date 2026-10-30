import pytest
from fastapi.testclient import TestClient

from app import language as lang
from app.main import app, catalog
from app.plan import Plan, execute

client = TestClient(app)


def plan(**kwargs) -> Plan:
    return Plan.model_validate(kwargs)


LIGHT = {"attr": "weight_kg", "op": "<=", "value": 1.4}
PLANS = [
    plan(kind="list", filters=[LIGHT, {"attr": "price", "op": "<", "value": 1000}], sort={"attr": "battery_h", "dir": "desc"}),
    plan(kind="list", filters=[{"attr": "display_in", "op": "=", "value": 14.0}, {"attr": "display_type", "op": "=", "value": "OLED"}],
         sort={"attr": "price", "dir": "asc"}),
    plan(kind="list", filters=[{"attr": "brand", "op": "=", "value": "Vela"}, {"attr": "delivery", "op": "=", "value": "tomorrow"}],
         sort={"attr": "rating", "dir": "desc"}),
    plan(kind="list", filters=[{"attr": "ram_gb", "op": ">=", "value": 16}, {"attr": "storage_gb", "op": "=", "value": 1024}],
         sort={"attr": "weight_kg", "dir": "asc"}),
    plan(kind="list", filters=[{"attr": "delivery", "op": "=", "value": "2-3 days"}], sort={"attr": "price", "dir": "desc"}),
    plan(kind="list", filters=[LIGHT, {"attr": "display_type", "op": "=", "value": "OLED"}], sort={"attr": "recommended", "dir": "desc"}),
    plan(kind="group", filters=[LIGHT], group_by="brand", metric="battery_per_100eur"),
    plan(kind="group", filters=[LIGHT, {"attr": "ram_gb", "op": "=", "value": 16}], group_by="brand", metric="battery_per_100eur"),
    plan(kind="group", filters=[{"attr": "display_type", "op": "=", "value": "OLED"}], group_by="brand", metric="avg_price"),
    plan(kind="group", filters=[], group_by="brand", metric="avg_rating"),
    plan(kind="group", filters=[{"attr": "price", "op": "<", "value": 1000}], group_by="brand", metric="count"),
    plan(kind="count", filters=[{"attr": "ram_gb", "op": "=", "value": 32}]),
    plan(kind="offers", product_id=2, max_price=949),
    plan(kind="offers", product_id=2, max_price=949, filters=[{"attr": "delivery", "op": "=", "value": "tomorrow"}]),
    plan(kind="offers", product_id=2),
]


def canonical(p: Plan) -> dict:
    data = p.model_dump()
    data["filters"] = sorted((f["attr"], f["op"], float(f["value"]) if isinstance(f["value"], (int, float)) else f["value"])
                             for f in data["filters"])
    return data


@pytest.mark.parametrize("p", PLANS, ids=lambda p: lang.question(p, catalog))
def test_verbalized_question_parses_back_to_the_same_plan(p):
    """P4: the question written for a click, typed in again, poses the same query."""
    parsed = lang.parse(lang.question(p, catalog), catalog)
    assert parsed is not None and canonical(parsed) == canonical(p)


@pytest.mark.parametrize("p", PLANS, ids=lambda p: lang.question(p, catalog))
def test_every_plan_is_answerable(p):
    result = execute(catalog, p)
    assert lang.interpretation(p, catalog).startswith("I'll")
    for followup in lang.followups(p, result, catalog):
        execute(catalog, followup)


def test_refinement_keeps_the_context():
    context = PLANS[0]
    refined = lang.parse("only with 16 GB RAM", catalog, context)
    assert refined.filter_value("ram_gb") == 16 and refined.filter_value("price") == 1000
    assert refined.sort == context.sort


def test_lists_are_sorted_by_recommendation_by_default():
    for text in ["Which OLED laptops are there?", "Show me lightweight laptops"]:
        assert lang.parse(text, catalog).sort.attr == "recommended", text
    opening = client.get("/api/start").json()
    assert opening["kind"] == "list" and opening["total"] == len(catalog.products) and opening["facets"] and opening["examples"]
    assert opening["rows"] == execute(catalog, plan(kind="list", sort={"attr": "recommended", "dir": "desc"}))["rows"]


def test_unanswerable_question_offers_examples():
    response = client.post("/api/ask", json={"text": "What is the weather tomorrow in Berlin?"}).json()
    assert response["kind"] == "unanswerable" and response["examples"]


def test_click_is_verbalized_and_facets_carry_plans():
    first = client.post("/api/ask", json={"text": "Which brands offer the most battery life per euro among lightweight laptops?"}).json()
    ram = next(f for f in first["facets"] if f["attr"] == "ram_gb")
    value = next(v for v in ram["values"] if v["value"] == 16)
    second = client.post("/api/query", json={"plan": value["plan"]}).json()
    assert second["question"] == "Which brands offer the most battery life per euro among lightweight laptops with 16 GB RAM?"
    assert all(row["members"] for row in second["answer"]["rows"])


def test_frontend_and_placeholder_images():
    assert "app.js" in client.get("/").text
    image = client.get("/img/1.svg")
    assert image.status_code == 200 and image.headers["content-type"].startswith("image/svg+xml")
    assert client.get("/img/999.svg").status_code == 404


def test_questions_refer_only_to_selected_products():
    ids = [1, 2, 5]
    for text in ["Which of them has the longest battery life?", "Which laptops are the lightest?",
                 "only with 16 GB RAM", "Compare these"]:
        response = client.post("/api/ask", json={"text": text, "selection": ids}).json()
        assert response["plan"]["ids"] == ids and {r["id"] for r in response["rows"]} <= set(ids), text
        assert "selected" in response["interpretation"]
    offers = client.post("/api/ask", json={"text": "Which shops offer it?", "selection": [2]}).json()
    assert offers["kind"] == "offers" and offers["plan"]["product_id"] == 2
    single = client.post("/api/ask", json={"text": "How heavy is it?", "selection": [2]}).json()
    assert [r["id"] for r in single["rows"]] == [2] and single["interpretation"].startswith("I'll look up the")


def test_delivery_condition_carries_over_to_selection_and_offers():
    context = lang.parse("Which laptops under €1,000 available for delivery tomorrow do you recommend?", catalog)
    plan = lang.parse("Which of them is the lightest?", catalog, context, [1, 2, 5])
    assert plan.filter_value("delivery") == "tomorrow" and "delivery tomorrow" in lang.interpretation(plan, catalog)
    offers = execute(catalog, Plan(kind="offers", product_id=2, filters=plan.filters))
    assert offers["rows"] and all(o["delivery_days"] == 1 for o in offers["rows"])


def test_product_page():
    data = client.get("/api/product/2").json()
    assert data["product"]["id"] == 2 and data["offers"]
    assert client.get("/api/product/999").status_code == 404



@pytest.mark.parametrize("text", lang.EXAMPLES)
def test_examples_are_understood_and_verbalized_as_typed(text):
    parsed = lang.parse(text, catalog)
    assert parsed is not None and lang.question(parsed, catalog) == text and execute(catalog, parsed)["rows"]


def test_vague_question_offers_unambiguous_candidates():
    a = client.post("/api/ask", json={"text": "Which laptop is best for students?"}).json()
    assert a["kind"] == "clarify" and len(a["candidates"]) == 3
    for c in a["candidates"]:
        # Each candidate is an executable plan whose question, typed in again, is no longer vague.
        assert c["sql"].startswith("SELECT") and c["total"] > 0
        assert lang.readings(c["question"], catalog) is None
        assert lang.parse(c["question"], catalog) == Plan.model_validate(c["plan"])
    chosen = client.post("/api/query", json={"plan": a["candidates"][1]["plan"]}).json()
    assert chosen["question"] == "Which lightweight laptops have the longest battery life?"


def test_likely_reading_is_answered_directly_and_stated():
    a = client.post("/api/ask", json={"text": "a good laptop for travel"}).json()
    assert a["kind"] == "list" and a["interpretation"].startswith("I read “for travel” as")
    assert a["followups"][0]["question"] == "Which lightweight laptops are the lightest?"


def test_explicit_criteria_are_not_vague():
    for text in ["Which laptops are rated best?", "the best cheap laptops", "good battery laptops"]:
        assert lang.readings(text, catalog) is None
    sel = client.post("/api/ask", json={"text": "Which of them is the best?", "selection": [1, 2, 3]}).json()
    assert sel["kind"] == "clarify" and all(c["plan"]["ids"] == [1, 2, 3] for c in sel["candidates"])
