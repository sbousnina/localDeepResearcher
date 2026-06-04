"""Supervisor graph — orchestrates clarification → team → parallel experts → joker → synthesis."""

import asyncio
from typing import Literal

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from shared.models import ClarifiedContext, Expert, ResearchResult
from agents.clarification import extract_clarified_context
from agents.expert_runner import run_expert
from agents.joker import run_joker
from agents.team_assembly import extract_expert_team
from supervisor.state import ResearchState, ResearchStateInput, ResearchStateOutput


# ── Helper ────────────────────────────────────────────────────────────────────

def _deserialize_context(state: ResearchState) -> ClarifiedContext | None:
    if state.clarified_context is None:
        return None
    if isinstance(state.clarified_context, ClarifiedContext):
        return state.clarified_context
    return ClarifiedContext(**state.clarified_context)


def _deserialize_experts(state: ResearchState) -> list[Expert]:
    result = []
    for e in state.expert_team:
        if isinstance(e, Expert):
            result.append(e)
        else:
            result.append(Expert(**e))
    return result


def _deserialize_results(state: ResearchState) -> list[ResearchResult]:
    result = []
    for r in state.expert_results:
        if isinstance(r, ResearchResult):
            result.append(r)
        else:
            result.append(ResearchResult(**r))
    return result


# ── Nodes ─────────────────────────────────────────────────────────────────────

async def extract_context_node(state: ResearchState, config: RunnableConfig) -> dict:
    """Extract structured ClarifiedContext from the clarification conversation."""
    context = await extract_clarified_context(state.clarification_messages)
    return {
        "clarified_context": context.model_dump(),
        "clarification_complete": True,
    }


async def extract_team_node(state: ResearchState, config: RunnableConfig) -> dict:
    """Extract structured expert team from the last assistant team proposal."""
    # Find the last assistant message that contains the team proposal
    last_proposal = ""
    for msg in reversed(state.clarification_messages):
        if msg.get("role") == "assistant":
            last_proposal = msg["content"]
            break

    experts = await extract_expert_team(last_proposal)
    return {
        "expert_team": [e.model_dump() for e in experts],
        "team_validated": True,
    }


async def run_expert_node(state: ResearchState, config: RunnableConfig) -> dict:
    """Run all expert research loops in parallel and collect results."""
    context = _deserialize_context(state)
    experts = _deserialize_experts(state)

    if not context or not experts:
        return {"expert_results": []}

    tasks = [run_expert(expert, context) for expert in experts]
    results: list[ResearchResult] = await asyncio.gather(*tasks)

    return {"expert_results": [r.model_dump() for r in results]}


async def run_joker_node(state: ResearchState, config: RunnableConfig) -> dict:
    """Run the Red Team agent against all expert results."""
    context = _deserialize_context(state)
    results = _deserialize_results(state)

    if not context or not results:
        return {"joker_report": ""}

    report = await run_joker(results, context)
    return {"joker_report": report}


# ── Routing ───────────────────────────────────────────────────────────────────

def route_after_clarification(
    state: ResearchState,
) -> Literal["extract_context", "extract_team", "run_experts"]:
    """Route based on which extraction step is needed next."""
    if not state.clarification_complete:
        return "extract_context"
    if not state.team_validated:
        return "extract_team"
    return "run_experts"


def route_after_team(
    state: ResearchState,
) -> Literal["run_experts", END]:
    if state.team_validated and state.expert_team:
        return "run_experts"
    return END


# ── Graph assembly ────────────────────────────────────────────────────────────

builder = StateGraph(
    ResearchState,
    input=ResearchStateInput,
    output=ResearchStateOutput,
)

builder.add_node("extract_context", extract_context_node)
builder.add_node("extract_team", extract_team_node)
builder.add_node("run_experts", run_expert_node)
builder.add_node("run_joker", run_joker_node)

# Edges
builder.add_edge(START, "extract_context")
builder.add_edge("extract_context", "extract_team")
builder.add_edge("extract_team", "run_experts")
builder.add_edge("run_experts", "run_joker")
builder.add_edge("run_joker", END)

supervisor_graph = builder.compile()
