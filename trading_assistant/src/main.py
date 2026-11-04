"""FastAPI routes. Run from the project root: uvicorn main:app --app-dir src"""
from dataclasses import asdict
from functools import lru_cache
from typing import Literal

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from langgraph.types import Command
from pydantic import BaseModel

load_dotenv()  # before any traced or LLM code

import tools  # noqa: E402
from graph import build_graph  # noqa: E402

app = FastAPI(title="Stock Trading Assistant (paper trading)")


class ChatRequest(BaseModel):
    thread_id: str
    message: str


class ResumeRequest(BaseModel):
    thread_id: str
    decision: Literal["yes", "no"]


@lru_cache
def get_graph():
    return build_graph()


def to_response(thread_id: str, state: dict) -> dict:
    if state.get("__interrupt__"):
        return {"status": "pending_approval", "thread_id": thread_id,
                "summary": state["__interrupt__"][0].value}
    return {"status": "reply", "reply": state["messages"][-1].content}


@app.post("/chat")
def chat(req: ChatRequest) -> dict:
    config = {"configurable": {"thread_id": req.thread_id}}
    state = get_graph().invoke({"messages": [{"role": "user", "content": req.message}]}, config=config)
    return to_response(req.thread_id, state)


@app.post("/chat/resume")
def resume(req: ResumeRequest) -> dict:
    graph = get_graph()
    config = {"configurable": {"thread_id": req.thread_id}}
    if not graph.get_state(config).next:
        raise HTTPException(409, "No pending approval for this thread")
    state = graph.invoke(Command(resume=req.decision), config=config)
    return to_response(req.thread_id, state)


@app.get("/portfolio")
def portfolio() -> dict:
    holdings = []
    for symbol, h in tools.store.get_holdings().items():
        quote = tools.provider.get_quote(symbol)
        holdings.append({**asdict(h), "price": quote.price, "price_source": quote.source,
                         "market_value": round(h.quantity * quote.price, 2)})
    cash = tools.store.get_cash()
    market_value = round(sum(h["market_value"] for h in holdings), 2)
    return {"cash": cash, "holdings": holdings, "market_value": market_value,
            "total_value": round(cash + market_value, 2)}


@app.get("/trades")
def trades() -> list[dict]:
    return [asdict(t) for t in tools.store.get_trades()]


@app.get("/health")
def health() -> dict:
    return {"ok": True}
