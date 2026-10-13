"""Local HTTP API (FastAPI). The Lambda handler in aws/handlers.py serves the same routes."""

from __future__ import annotations

from datetime import date

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from . import assistant, bedrock
from .config import MAX_QUESTION_CHARS, Settings
from .data import GoldCache
from .store import LocalLog

settings = Settings.from_env()
cache = GoldCache(settings.gold)
log_store = LocalLog()
app = FastAPI(title="Sodhnus", description="Rainfall questions about Nepal, answered only from verified data.")


class Question(BaseModel):
    question: str = Field(..., max_length=MAX_QUESTION_CHARS * 2)


class Feedback(BaseModel):
    id: str
    helpful: bool


@app.post("/ask")
def ask(q: Question) -> dict:
    client = bedrock.client(settings.region) if settings.backend == "bedrock" else None
    a = assistant.ask(
        q.question,
        cache.get(),
        backend=settings.backend,
        bedrock_client=client,
        model_id=settings.model_id,
        guardrail_id=settings.guardrail_id,
        guardrail_version=settings.guardrail_version,
    )
    return {"id": log_store.put(a.record()), **a.public()}


@app.post("/feedback")
def feedback(f: Feedback) -> dict:
    if not log_store.feedback(f.id, f.helpful):
        raise HTTPException(404, "unknown id")
    return {"ok": True}


@app.get("/health")
def health() -> dict:
    gold = cache.get()
    age = (date.today() - gold.latest_day).days
    return {"ok": True, "backend": settings.backend, "data_through": gold.latest_day.isoformat(), "data_age_days": age}
