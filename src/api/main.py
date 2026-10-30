"""Thin FastAPI wrapper over src.policy.recommend. Run: uvicorn src.api.main:app --reload"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from src.policy.recommend import recommend

app = FastAPI(title="NPS risk-budget glide-path recommender", version="0.2")


class RecommendRequest(BaseModel):
    tier: str | None = Field(None, description="low | medium | high income-volatility tier")
    employment_type: str | None = Field(None, description="regular_salaried | casual_labour | self_employed")
    epsilon: float = Field(0.05, ge=0, le=1, description="max tolerated P(account < 90% of contributions)")
    n_trials: int = Field(200, ge=20, le=1000)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/recommend")
def post_recommend(req: RecommendRequest):
    try:
        return recommend(req.tier, req.employment_type, req.epsilon, req.n_trials)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
