"""Dialog-First product search: FastAPI backend around the answers of `service.py`.

Run locally:  uvicorn app.main:app --reload
"""

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from . import service
from .catalog import placeholder_svg
from .service import AskIn, QueryIn, catalog

BASE_DIR = Path(__file__).resolve().parent.parent

app = FastAPI(title="Dialog-First product search", docs_url=None, redoc_url=None, openapi_url=None)


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/api/start")
def start():
    return service.start()


@app.post("/api/ask")
def ask(body: AskIn):
    return service.ask(body)


@app.post("/api/query")
def query(body: QueryIn):
    try:
        return service.query(body)
    except service.UnknownProduct:
        raise HTTPException(404, "Unknown product")


@app.post("/api/verbalize")
def verbalize(body: QueryIn):
    return service.verbalize(body)


@app.get("/api/product/{product_id}")
def product(product_id: int):
    try:
        return service.product(product_id)
    except service.UnknownProduct:
        raise HTTPException(404, "Unknown product")


@app.get("/img/{product_id}.svg")
def image(product_id: int):
    product = catalog.by_id.get(product_id)
    if product is None:
        raise HTTPException(404, "Unknown product")
    return Response(placeholder_svg(product), media_type="image/svg+xml",
                    headers={"Cache-Control": "public, max-age=86400"})


app.mount("/", StaticFiles(directory=BASE_DIR / "static", html=True), name="static")
