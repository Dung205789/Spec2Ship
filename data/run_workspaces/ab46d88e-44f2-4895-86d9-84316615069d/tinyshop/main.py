from fastapi import FastAPI
from pydantic import BaseModel

from tinyshop.pricing import apply_discount

app = FastAPI(title="tinyshop")


class DiscountIn(BaseModel):
    total_cents: int
    percent: int


@app.post("/discount")
def discount(payload: DiscountIn) -> dict:
    return {"discounted_cents": apply_discount(payload.total_cents, payload.percent)}


@app.get("/health")
def health():
    return {"status": "ok"}
