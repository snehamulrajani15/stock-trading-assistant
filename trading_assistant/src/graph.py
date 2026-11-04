"""LangGraph app: router -> deterministic handler, or tool agent with human approval."""
from typing import Annotated, Literal, TypedDict

from langchain.chat_models import init_chat_model
from langchain_core.messages import AIMessage, SystemMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from pydantic import BaseModel

import handlers
from tools import tools

MIN_CONFIDENCE = 0.6

Intent = Literal["portfolio_value", "holdings", "trade_history", "pnl", "quote", "trade", "other"]
HANDLED_INTENTS = {"portfolio_value", "holdings", "trade_history", "pnl", "quote"}

ROUTER_PROMPT = """Classify the user's latest message into exactly one intent:
- portfolio_value: total worth of the portfolio or account
- holdings: which stocks/shares the user owns
- trade_history: past trades or orders
- pnl: profit/loss or performance (of one stock or overall)
- quote: the current price of a stock
- trade: the user wants to buy or sell shares
- other: anything else, including price arithmetic or general questions
Also extract the stock ticker symbol if the message names one single stock (else null),
and give your confidence between 0 and 1."""

AGENT_PROMPT = """You are a paper-trading assistant. This is a simulation, not financial advice.
- Get prices only from the get_stock_price tool. Never guess or invent prices.
- To buy or sell, call place_orders ONCE with ALL orders in a single list. Never call it once per stock.
- Do not do money math for orders yourself: report the amounts returned by the tools.
- If the user does not give a quantity or a ticker, ask for it instead of assuming."""


class RouterOutput(BaseModel):
    intent: Intent
    symbol: str | None = None
    confidence: float


class State(TypedDict):
    messages: Annotated[list, add_messages]
    intent: str
    symbol: str | None


def build_graph(llm=None):
    llm = llm or init_chat_model(model="gpt-4o-mini", temperature=0)
    agent_llm = llm.bind_tools(tools)
    classifier = llm.with_structured_output(RouterOutput)

    def router(state: State) -> dict:
        result = classifier.invoke([
            SystemMessage(ROUTER_PROMPT),
            state["messages"][-1],
        ])
        intent = result.intent if result.confidence >= MIN_CONFIDENCE else "other"
        return {"intent": intent, "symbol": result.symbol}

    def route(state: State) -> str:
        return "handler" if state["intent"] in HANDLED_INTENTS else "agent"

    def handler(state: State) -> dict:
        intent, symbol = state["intent"], state["symbol"]
        if intent == "portfolio_value":
            reply = handlers.portfolio_value()
        elif intent == "holdings":
            reply = handlers.holdings()
        elif intent == "trade_history":
            reply = handlers.trade_history(symbol)
        elif intent == "pnl":
            reply = handlers.pnl(symbol)
        else:
            reply = handlers.quote(symbol)
        return {"messages": [AIMessage(reply)]}

    def agent(state: State) -> dict:
        messages = [SystemMessage(AGENT_PROMPT)] + state["messages"]
        return {"messages": [agent_llm.invoke(messages)]}

    builder = StateGraph(State)
    builder.add_node("router", router)
    builder.add_node("handler", handler)
    builder.add_node("agent", agent)
    builder.add_node("tools", ToolNode(tools))

    builder.add_edge(START, "router")
    builder.add_conditional_edges("router", route, ["handler", "agent"])
    builder.add_edge("handler", END)
    builder.add_conditional_edges("agent", tools_condition)
    builder.add_edge("tools", "agent")

    return builder.compile(checkpointer=MemorySaver())
