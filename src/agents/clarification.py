"""Clarification agent — multi-turn interviewer that builds a ClarifiedContext."""

import json
import os

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_ollama import ChatOllama

from shared.models import ClarifiedContext
from supervisor.prompts import CLARIFICATION_EXTRACTION_PROMPT, CLARIFICATION_SYSTEM_PROMPT

# Minimum confidence before we consider clarification complete
_CONFIDENCE_THRESHOLD = 0.80

# Marker injected by the LLM when it is ready to proceed; used to detect phase transition
CLARIFICATION_READY_MARKER = "📌"


def get_clarification_llm() -> ChatOllama:
    url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    model = os.getenv("LOCAL_LLM", "qwen3:14b").split("/")[-1]
    return ChatOllama(base_url=url, model=model, temperature=0.3)


def build_langchain_messages(
    conversation: list[dict],
) -> list:
    """Convert raw {role, content} dicts to LangChain message objects."""
    msgs = [SystemMessage(content=CLARIFICATION_SYSTEM_PROMPT)]
    for msg in conversation:
        if msg["role"] == "user":
            msgs.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "assistant":
            msgs.append(AIMessage(content=msg["content"]))
    return msgs


async def stream_clarification_turn(
    conversation: list[dict],
):
    """Stream one clarification turn; yields text chunks."""
    llm = get_clarification_llm()
    msgs = build_langchain_messages(conversation)
    async for chunk in llm.astream(msgs):
        if chunk.content:
            yield chunk.content


def is_ready_to_proceed(assistant_message: str) -> bool:
    """True when the LLM has produced its structured summary and asked for confirmation."""
    return CLARIFICATION_READY_MARKER in assistant_message


async def extract_clarified_context(conversation: list[dict]) -> ClarifiedContext:
    """Parse the conversation into a structured ClarifiedContext via a dedicated LLM call."""
    llm = get_clarification_llm()
    conversation_text = "\n".join(
        f"{m['role'].upper()}: {m['content']}" for m in conversation
    )
    prompt = CLARIFICATION_EXTRACTION_PROMPT.format(conversation=conversation_text)
    result = await llm.ainvoke([HumanMessage(content=prompt)])

    raw = result.content.strip()
    # Strip markdown fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]

    try:
        data = json.loads(raw)
        return ClarifiedContext(**data)
    except Exception:
        # Fallback: build from what we have
        return ClarifiedContext(
            situation="À déterminer",
            goal="À déterminer",
            success_criteria="À définir",
            constraints="Inconnues",
            main_blocker="Non identifié",
            confidence_score=0.5,
        )


def clarified_context_to_text(ctx: ClarifiedContext) -> str:
    return (
        f"Situation : {ctx.situation}\n"
        f"Objectif : {ctx.goal}\n"
        f"Succès (30/90j) : {ctx.success_criteria}\n"
        f"Contraintes : {ctx.constraints}\n"
        f"Principal bloqueur : {ctx.main_blocker}"
    )
