"""Synthesizer agent — two-phase: vision (3-5 bullets) then full detail report."""

import os
from typing import AsyncGenerator

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama

from shared.models import ClarifiedContext, ResearchResult
from agents.clarification import clarified_context_to_text
from agents.joker import _format_expert_summaries
from supervisor.prompts import DETAIL_SYNTHESIS_PROMPT, VISION_ADJUSTMENT_PROMPT, VISION_SYNTHESIS_PROMPT


def get_synthesis_llm() -> ChatOllama:
    url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    model = os.getenv("LOCAL_LLM", "qwen3:14b").split("/")[-1]
    return ChatOllama(base_url=url, model=model, temperature=0.2)


# ── Phase 3a : Vision ─────────────────────────────────────────────────────────

async def stream_vision_synthesis(
    expert_results: list[ResearchResult],
    joker_report: str,
    context: ClarifiedContext,
) -> AsyncGenerator[str, None]:
    """Stream the high-level strategic vision (3-5 bullets only)."""
    llm = get_synthesis_llm()
    prompt = VISION_SYNTHESIS_PROMPT.format(
        expert_summaries=_format_expert_summaries(expert_results),
        joker_report=joker_report,
        clarified_context=clarified_context_to_text(context),
    )
    msgs = [SystemMessage(content=prompt), HumanMessage(content="Produis la direction stratégique.")]

    async for chunk in llm.astream(msgs):
        if chunk.content:
            yield chunk.content


async def stream_vision_adjustment(
    current_vision: str,
    feedback: str,
) -> AsyncGenerator[str, None]:
    """Stream an adjusted vision based on user feedback."""
    llm = get_synthesis_llm()
    prompt = VISION_ADJUSTMENT_PROMPT.format(
        current_vision=current_vision, feedback=feedback
    )
    msgs = [SystemMessage(content=prompt), HumanMessage(content=feedback)]

    async for chunk in llm.astream(msgs):
        if chunk.content:
            yield chunk.content


# ── Phase 3b : Detail ─────────────────────────────────────────────────────────

async def stream_detail_synthesis(
    vision_summary: str,
    expert_results: list[ResearchResult],
    joker_report: str,
    context: ClarifiedContext,
) -> AsyncGenerator[str, None]:
    """Stream the full structured report (CATs, roadmap, don't-do list)."""
    llm = get_synthesis_llm()

    # Consolidate all sources
    all_sources: list[str] = []
    seen: set[str] = set()
    for r in expert_results:
        for s in r.sources:
            if s not in seen:
                seen.add(s)
                all_sources.append(s)
    sources_text = "\n".join(all_sources) if all_sources else "*Aucune source externe collectée.*"

    prompt = DETAIL_SYNTHESIS_PROMPT.format(
        vision_summary=vision_summary,
        expert_summaries=_format_expert_summaries(expert_results),
        joker_report=joker_report,
        clarified_context=clarified_context_to_text(context),
        sources_placeholder=sources_text,
    )
    msgs = [SystemMessage(content=prompt), HumanMessage(content="Produis le rapport détaillé complet.")]

    async for chunk in llm.astream(msgs):
        if chunk.content:
            yield chunk.content
