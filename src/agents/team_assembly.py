"""Team assembly agent — proposes and adjusts the expert team."""

import json
import os
from typing import AsyncGenerator

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_ollama import ChatOllama

from shared.models import ClarifiedContext, Expert
from agents.clarification import clarified_context_to_text
from supervisor.prompts import (
    TEAM_ADJUSTMENT_PROMPT,
    TEAM_ASSEMBLY_PROMPT,
    TEAM_EXTRACTION_PROMPT,
)

TEAM_READY_MARKER = "📌"


def get_team_llm() -> ChatOllama:
    url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    model = os.getenv("LOCAL_LLM", "qwen3:14b").split("/")[-1]
    return ChatOllama(base_url=url, model=model, temperature=0.3)


async def stream_team_proposal(
    clarified_context: ClarifiedContext,
) -> AsyncGenerator[str, None]:
    """Stream the initial team proposal."""
    llm = get_team_llm()
    context_text = clarified_context_to_text(clarified_context)
    prompt = TEAM_ASSEMBLY_PROMPT.format(clarified_context=context_text)
    msgs = [SystemMessage(content=prompt), HumanMessage(content="Propose l'équipe.")]

    async for chunk in llm.astream(msgs):
        if chunk.content:
            yield chunk.content


async def stream_team_adjustment(
    current_proposal: str,
    feedback: str,
) -> AsyncGenerator[str, None]:
    """Stream an updated team proposal based on user feedback."""
    llm = get_team_llm()
    prompt = TEAM_ADJUSTMENT_PROMPT.format(
        current_team=current_proposal, feedback=feedback
    )
    msgs = [SystemMessage(content=prompt), HumanMessage(content=feedback)]

    async for chunk in llm.astream(msgs):
        if chunk.content:
            yield chunk.content


async def extract_expert_team(team_proposal: str) -> list[Expert]:
    """Parse the team proposal text into structured Expert objects."""
    llm = get_team_llm()
    prompt = TEAM_EXTRACTION_PROMPT.format(team_proposal=team_proposal)
    result = await llm.ainvoke([HumanMessage(content=prompt)])

    raw = result.content.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]

    try:
        data = json.loads(raw)
        return [Expert(**item) for item in data]
    except Exception:
        # Fallback: single generic expert
        return [
            Expert(
                name="Alex Dupont",
                role="Expert Recherche Généraliste",
                methodology="First Principles",
                research_angle=f"Analyse complète de la situation",
            )
        ]


def expert_team_to_text(experts: list[Expert]) -> str:
    lines = []
    for i, e in enumerate(experts, 1):
        lines.append(
            f"{i}. **{e.name}** — {e.role}\n"
            f"   Méthodologie : {e.methodology}\n"
            f"   Angle : {e.research_angle}"
        )
    return "\n\n".join(lines)
