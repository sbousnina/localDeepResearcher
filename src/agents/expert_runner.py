"""Expert runner — wraps the existing research sub-graph for one expert."""

import os

from shared.models import ClarifiedContext, Expert, ResearchResult
from agents.clarification import clarified_context_to_text
from supervisor.prompts import EXPERT_PERSONA_PROMPT


def _build_research_config(expert: Expert, persona: str) -> dict:
    return {
        "configurable": {
            "max_web_research_loops": int(os.getenv("MAX_WEB_RESEARCH_LOOPS", 3)),
            "local_llm": os.getenv("LOCAL_LLM", "qwen3:14b").split("/")[-1],
            "llm_provider": os.getenv("LLM_PROVIDER", "ollama"),
            "search_api": os.getenv("SEARCH_API", "searxng"),
            "ollama_base_url": os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            "fetch_full_page": os.getenv("FETCH_FULL_PAGE", "false").lower() == "true",
            "research_persona": persona,
        }
    }


def _build_research_topic(expert: Expert, context: ClarifiedContext) -> str:
    context_text = clarified_context_to_text(context)
    return (
        f"[{expert.role} — {expert.methodology}]\n"
        f"Contexte : {context_text}\n\n"
        f"Question spécifique à investiguer : {expert.research_angle}"
    )


def _extract_sources(raw_summary: str) -> list[str]:
    sources: list[str] = []
    if "### Sources:" in raw_summary:
        sources_section = raw_summary.split("### Sources:")[-1]
        for line in sources_section.strip().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                sources.append(line)
    return sources


def _extract_key_insights(raw_summary: str) -> list[str]:
    """Pull bullet-point sentences from the summary as key insights (max 5)."""
    insights: list[str] = []
    for line in raw_summary.splitlines():
        stripped = line.strip()
        if stripped.startswith(("- ", "* ", "• ")) and len(stripped) > 20:
            insights.append(stripped.lstrip("-*• ").strip())
        if len(insights) >= 5:
            break
    return insights


async def run_expert(
    expert: Expert,
    context: ClarifiedContext,
) -> ResearchResult:
    """Run the research sub-graph for a single expert and return a ResearchResult."""
    # Import here to avoid circular imports at module level
    from ollama_deep_researcher.graph import graph  # type: ignore

    persona = EXPERT_PERSONA_PROMPT.format(
        name=expert.name,
        role=expert.role,
        methodology=expert.methodology,
        clarified_context=clarified_context_to_text(context),
        research_angle=expert.research_angle,
    )
    topic = _build_research_topic(expert, context)
    config = _build_research_config(expert, persona)

    result = await graph.ainvoke({"research_topic": topic}, config=config)
    raw_summary: str = result.get("running_summary", "")

    # Split summary body from sources
    summary_body = raw_summary
    if "### Sources:" in raw_summary:
        summary_body = raw_summary.split("### Sources:")[0].strip()

    return ResearchResult(
        expert_name=expert.name,
        expert_role=expert.role,
        methodology=expert.methodology,
        summary=summary_body,
        sources=_extract_sources(raw_summary),
        key_insights=_extract_key_insights(summary_body),
    )
