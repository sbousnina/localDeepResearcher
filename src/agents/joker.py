"""Joker / Red Team agent — challenges and audits all expert contributions."""

import os
from typing import AsyncGenerator

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama

from shared.models import ClarifiedContext, ResearchResult
from agents.clarification import clarified_context_to_text
from supervisor.prompts import JOKER_SYSTEM_PROMPT


def get_joker_llm() -> ChatOllama:
    url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    model = os.getenv("LOCAL_LLM", "qwen3:14b").split("/")[-1]
    # Slightly higher temperature: the joker should think divergently
    return ChatOllama(base_url=url, model=model, temperature=0.5)


def _format_expert_summaries(results: list[ResearchResult]) -> str:
    parts = []
    for r in results:
        insights = "\n".join(f"  - {i}" for i in r.key_insights) if r.key_insights else "  (aucun insight extrait)"
        parts.append(
            f"### {r.expert_name} — {r.expert_role} ({r.methodology})\n"
            f"{r.summary[:1500]}\n\n"
            f"**Insights clés :**\n{insights}"
        )
    return "\n\n---\n\n".join(parts)


async def stream_joker_report(
    expert_results: list[ResearchResult],
    context: ClarifiedContext,
) -> AsyncGenerator[str, None]:
    """Stream the Red Team challenge report."""
    llm = get_joker_llm()
    expert_summaries = _format_expert_summaries(expert_results)
    context_text = clarified_context_to_text(context)

    system_prompt = JOKER_SYSTEM_PROMPT.format(
        expert_summaries=expert_summaries,
        clarified_context=context_text,
    )
    msgs = [
        SystemMessage(content=system_prompt),
        HumanMessage(content="Produis ton rapport Red Team maintenant."),
    ]

    async for chunk in llm.astream(msgs):
        if chunk.content:
            yield chunk.content


async def run_joker(
    expert_results: list[ResearchResult],
    context: ClarifiedContext,
) -> str:
    """Run the joker agent and return the full report string (non-streaming)."""
    full_report = ""
    async for chunk in stream_joker_report(expert_results, context):
        full_report += chunk
    return full_report
