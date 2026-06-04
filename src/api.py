import os
import sys
import time
from enum import Enum
from typing import AsyncGenerator, List

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from shared.models import ClarifiedContext, ResearchResult
from shared.sse import done_chunk, make_chunk, new_completion_id
from shared.validation import detect_adjustment_intent, detect_validation_intent
from agents.clarification import (
    CLARIFICATION_READY_MARKER,
    extract_clarified_context,
    stream_clarification_turn,
)
from agents.team_assembly import (
    TEAM_READY_MARKER,
    extract_expert_team,
    expert_team_to_text,
    stream_team_adjustment,
    stream_team_proposal,
)
from agents.joker import run_joker
from agents.synthesizer import (
    stream_detail_synthesis,
    stream_vision_adjustment,
    stream_vision_synthesis,
)

# ── App setup ─────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Multi-Agent Expert Team — OpenAI-Compatible API",
    description="Système multi-agents parallèles avec clarification, Red Team, et synthèse en deux phases.",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Conversation state machine ────────────────────────────────────────────────

class ConvState(Enum):
    CLARIFYING        = "clarifying"
    TEAM_PROPOSAL     = "team_proposal"
    TEAM_ADJUSTING    = "team_adjusting"
    EXECUTING         = "executing"
    VISION_PROPOSAL   = "vision_proposal"
    VISION_ADJUSTING  = "vision_adjusting"
    DETAIL_EXECUTING  = "detail_executing"
    DONE              = "done"


# Markers embedded in assistant messages to encode state transitions
_MARKER_CLARIFICATION_DONE = "<!-- STATE:CLARIFICATION_DONE -->"
_MARKER_TEAM_PROPOSED       = "<!-- STATE:TEAM_PROPOSED -->"
_MARKER_VISION_PROPOSED     = "<!-- STATE:VISION_PROPOSED -->"
_MARKER_DETAIL_DONE         = "<!-- STATE:DETAIL_DONE -->"
# JSON payload markers
_MARKER_CONTEXT_JSON  = "<!-- CONTEXT_JSON:"
_MARKER_RESULTS_JSON  = "<!-- RESULTS_JSON:"
_MARKER_JOKER_JSON    = "<!-- JOKER_JSON:"
_MARKER_VISION_TEXT   = "<!-- VISION_TEXT:"
_MARKER_MARKER_END    = "-->"


def _find_marker(messages: list, marker: str) -> str | None:
    """Return the content after a given marker in any assistant message."""
    for msg in messages:
        if msg.role == "assistant" and marker in msg.content:
            start = msg.content.index(marker) + len(marker)
            end = msg.content.index(_MARKER_MARKER_END, start)
            return msg.content[start:end].strip()
    return None


def detect_conv_state(messages: list, is_direct: bool) -> ConvState:
    """Infer conversation state from message history markers."""
    if is_direct:
        return ConvState.EXECUTING

    last_user = messages[-1].content.strip() if messages else ""
    last_assistant = ""
    for msg in reversed(messages):
        if msg.role == "assistant":
            last_assistant = msg.content
            break

    has_clarification_done = any(
        _MARKER_CLARIFICATION_DONE in m.content
        for m in messages if m.role == "assistant"
    )
    has_team_proposed = any(
        _MARKER_TEAM_PROPOSED in m.content
        for m in messages if m.role == "assistant"
    )
    has_vision_proposed = any(
        _MARKER_VISION_PROPOSED in m.content
        for m in messages if m.role == "assistant"
    )
    has_detail_done = any(
        _MARKER_DETAIL_DONE in m.content
        for m in messages if m.role == "assistant"
    )

    if has_detail_done:
        return ConvState.DONE

    if has_vision_proposed:
        if detect_validation_intent(last_user):
            return ConvState.DETAIL_EXECUTING
        return ConvState.VISION_ADJUSTING

    if has_team_proposed:
        if detect_validation_intent(last_user):
            return ConvState.EXECUTING
        return ConvState.TEAM_ADJUSTING

    if has_clarification_done:
        # Clarification done, team not yet proposed
        return ConvState.TEAM_PROPOSAL

    return ConvState.CLARIFYING


# ── Data schemas ──────────────────────────────────────────────────────────────

class Message(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[Message]
    stream: bool = False
    temperature: float = 0.7
    max_tokens: int = 8192


class ModelInfo(BaseModel):
    id: str
    object: str = "model"
    created: int = Field(default_factory=lambda: int(time.time()))
    owned_by: str = "multi-agent-team"


class ModelList(BaseModel):
    object: str = "list"
    data: List[ModelInfo]


# ── Streaming generators ───────────────────────────────────────────────────────

async def _stream(
    gen: AsyncGenerator[str, None],
    model_id: str,
    extra_hidden: str = "",
) -> AsyncGenerator[str, None]:
    """Wrap an agent generator as SSE chunks, appending hidden state markers."""
    cid = new_completion_id()
    async for text in gen:
        yield make_chunk(text, model_id, cid)
    if extra_hidden:
        yield make_chunk(extra_hidden, model_id, cid)
    yield done_chunk()


async def clarification_stream(
    messages: list[Message],
    model_id: str,
) -> AsyncGenerator[str, None]:
    conversation = [{"role": m.role, "content": m.content} for m in messages]
    cid = new_completion_id()
    full_response = ""

    async for chunk in stream_clarification_turn(conversation):
        full_response += chunk
        yield make_chunk(chunk, model_id, cid)

    # If LLM produced its ready marker, embed the state transition
    if CLARIFICATION_READY_MARKER in full_response:
        # Extract context and embed it hidden for downstream use
        context = await extract_clarified_context(conversation + [{"role": "assistant", "content": full_response}])
        import json
        hidden = (
            f"\n{_MARKER_CLARIFICATION_DONE}\n"
            f"{_MARKER_CONTEXT_JSON}{json.dumps(context.model_dump())}{_MARKER_MARKER_END}"
        )
        yield make_chunk(hidden, model_id, cid)

    yield done_chunk()


async def team_proposal_stream(
    messages: list[Message],
    model_id: str,
) -> AsyncGenerator[str, None]:
    context_json = _find_marker(messages, _MARKER_CONTEXT_JSON)
    if not context_json:
        yield make_chunk("❌ Contexte de clarification introuvable.", model_id, new_completion_id())
        yield done_chunk()
        return

    import json
    context = ClarifiedContext(**json.loads(context_json))
    cid = new_completion_id()

    async for chunk in stream_team_proposal(context):
        yield make_chunk(chunk, model_id, cid)

    yield make_chunk(f"\n{_MARKER_TEAM_PROPOSED}", model_id, cid)
    yield done_chunk()


async def team_adjustment_stream(
    messages: list[Message],
    model_id: str,
) -> AsyncGenerator[str, None]:
    last_proposal = ""
    for msg in reversed(messages):
        if msg.role == "assistant" and _MARKER_TEAM_PROPOSED in msg.content:
            last_proposal = msg.content.replace(_MARKER_TEAM_PROPOSED, "").strip()
            break

    feedback = messages[-1].content
    cid = new_completion_id()

    async for chunk in stream_team_adjustment(last_proposal, feedback):
        yield make_chunk(chunk, model_id, cid)

    yield make_chunk(f"\n{_MARKER_TEAM_PROPOSED}", model_id, cid)
    yield done_chunk()


async def execution_stream(
    messages: list[Message],
    model_id: str,
    is_direct: bool,
    direct_topic: str = "",
) -> AsyncGenerator[str, None]:
    cid = new_completion_id()
    import json

    # ── Resolve context + team ────────────────────────────────────────────────
    if is_direct:
        from shared.models import Expert
        context = ClarifiedContext(
            situation=direct_topic,
            goal=direct_topic,
            success_criteria="À définir",
            constraints="Non spécifiées",
            main_blocker="Non identifié",
            confidence_score=1.0,
        )
        experts = [
            Expert(
                name="Alex Dupont",
                role="Expert Recherche Généraliste",
                methodology="First Principles",
                research_angle=direct_topic,
            )
        ]
    else:
        context_json = _find_marker(messages, _MARKER_CONTEXT_JSON)
        if not context_json:
            yield make_chunk("❌ Contexte introuvable.", model_id, cid)
            yield done_chunk()
            return
        context = ClarifiedContext(**json.loads(context_json))

        # Extract team from last proposed team message
        last_team_msg = ""
        for msg in reversed(messages):
            if msg.role == "assistant" and _MARKER_TEAM_PROPOSED in msg.content:
                last_team_msg = msg.content
                break
        experts = await extract_expert_team(last_team_msg)

    # ── Phase 2 : Parallel expert research ───────────────────────────────────
    yield make_chunk("🚀 **Lancement de la recherche multi-agents...**\n\n", model_id, cid)

    for e in experts:
        yield make_chunk(
            f"▶ **{e.name}** ({e.role}) — Méthodologie : *{e.methodology}*\n"
            f"   Angle : {e.research_angle}\n\n",
            model_id, cid
        )

    import asyncio
    from agents.expert_runner import run_expert

    tasks = [run_expert(expert, context) for expert in experts]
    expert_results: list[ResearchResult] = await asyncio.gather(*tasks)

    yield make_chunk(f"\n✅ **{len(expert_results)} expert(s) ont terminé leur recherche.**\n\n", model_id, cid)

    # ── Phase 2b : Joker ─────────────────────────────────────────────────────
    yield make_chunk("🃏 **Agent Red Team en cours d'analyse...**\n\n", model_id, cid)
    joker_report = await run_joker(expert_results, context)
    yield make_chunk("✅ **Rapport Red Team prêt.**\n\n", model_id, cid)

    # ── Phase 3a : Vision ────────────────────────────────────────────────────
    yield make_chunk("---\n\n🧭 **Synthèse de la direction stratégique...**\n\n", model_id, cid)
    vision_text = ""
    async for chunk in stream_vision_synthesis(expert_results, joker_report, context):
        vision_text += chunk
        yield make_chunk(chunk, model_id, cid)

    # Embed hidden state for downstream detail phase
    results_payload = json.dumps([r.model_dump() for r in expert_results])
    hidden = (
        f"\n{_MARKER_VISION_PROPOSED}"
        f"\n{_MARKER_RESULTS_JSON}{results_payload}{_MARKER_MARKER_END}"
        f"\n{_MARKER_JOKER_JSON}{joker_report}{_MARKER_MARKER_END}"
        f"\n{_MARKER_CONTEXT_JSON}{json.dumps(context.model_dump())}{_MARKER_MARKER_END}"
        f"\n{_MARKER_VISION_TEXT}{vision_text}{_MARKER_MARKER_END}"
    )
    yield make_chunk(hidden, model_id, cid)
    yield done_chunk()


async def vision_adjustment_stream(
    messages: list[Message],
    model_id: str,
) -> AsyncGenerator[str, None]:
    cid = new_completion_id()
    import json

    current_vision = _find_marker(messages, _MARKER_VISION_TEXT) or ""
    feedback = messages[-1].content
    new_vision = ""

    async for chunk in stream_vision_adjustment(current_vision, feedback):
        new_vision += chunk
        yield make_chunk(chunk, model_id, cid)

    # Preserve other hidden markers, update vision
    results_json = _find_marker(messages, _MARKER_RESULTS_JSON) or "[]"
    joker_json = _find_marker(messages, _MARKER_JOKER_JSON) or ""
    context_json = _find_marker(messages, _MARKER_CONTEXT_JSON) or "{}"

    hidden = (
        f"\n{_MARKER_VISION_PROPOSED}"
        f"\n{_MARKER_RESULTS_JSON}{results_json}{_MARKER_MARKER_END}"
        f"\n{_MARKER_JOKER_JSON}{joker_json}{_MARKER_MARKER_END}"
        f"\n{_MARKER_CONTEXT_JSON}{context_json}{_MARKER_MARKER_END}"
        f"\n{_MARKER_VISION_TEXT}{new_vision}{_MARKER_MARKER_END}"
    )
    yield make_chunk(hidden, model_id, cid)
    yield done_chunk()


async def detail_execution_stream(
    messages: list[Message],
    model_id: str,
) -> AsyncGenerator[str, None]:
    cid = new_completion_id()
    import json

    context_json = _find_marker(messages, _MARKER_CONTEXT_JSON) or "{}"
    results_json = _find_marker(messages, _MARKER_RESULTS_JSON) or "[]"
    joker_report = _find_marker(messages, _MARKER_JOKER_JSON) or ""
    vision_text = _find_marker(messages, _MARKER_VISION_TEXT) or ""

    context = ClarifiedContext(**json.loads(context_json))
    expert_results = [ResearchResult(**r) for r in json.loads(results_json)]

    yield make_chunk("📋 **Génération du rapport détaillé complet...**\n\n", model_id, cid)

    async for chunk in stream_detail_synthesis(vision_text, expert_results, joker_report, context):
        yield make_chunk(chunk, model_id, cid)

    yield make_chunk(f"\n{_MARKER_DETAIL_DONE}", model_id, cid)
    yield done_chunk()


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/v1/models", response_model=ModelList)
async def list_models():
    models = [
        ModelInfo(id="local-deep-researcher"),
        ModelInfo(id="deep-researcher-general"),
        ModelInfo(id="deep-researcher-marketing"),
        ModelInfo(id="deep-researcher-strategy"),
        ModelInfo(id="deep-researcher-tech"),
    ]
    return ModelList(data=models)


@app.post("/v1/chat/completions")
async def chat_completions(req: ChatCompletionRequest):
    if not req.messages:
        raise HTTPException(status_code=400, detail="La liste de messages est vide.")

    # ── Direct mode bypass ────────────────────────────────────────────────────
    is_direct = False
    direct_topic = ""
    first_content = req.messages[0].content.strip()
    for prefix in ("!fast ", "/direct "):
        if first_content.lower().startswith(prefix):
            is_direct = True
            direct_topic = first_content[len(prefix):].strip()
            break

    state = detect_conv_state(req.messages, is_direct)

    if not req.stream:
        raise HTTPException(
            status_code=400,
            detail="Seul le mode streaming est supporté. Activez stream=true.",
        )

    # ── Route to the correct generator ───────────────────────────────────────
    if state == ConvState.CLARIFYING:
        gen = clarification_stream(req.messages, req.model)

    elif state == ConvState.TEAM_PROPOSAL:
        gen = team_proposal_stream(req.messages, req.model)

    elif state == ConvState.TEAM_ADJUSTING:
        gen = team_adjustment_stream(req.messages, req.model)

    elif state == ConvState.EXECUTING:
        gen = execution_stream(req.messages, req.model, is_direct, direct_topic)

    elif state == ConvState.VISION_ADJUSTING:
        gen = vision_adjustment_stream(req.messages, req.model)

    elif state == ConvState.DETAIL_EXECUTING:
        gen = detail_execution_stream(req.messages, req.model)

    else:
        # DONE or unknown — echo a short message
        async def _done_gen():
            cid = new_completion_id()
            yield make_chunk("✅ La session est terminée. Démarrez une nouvelle conversation.", req.model, cid)
            yield done_chunk()
        gen = _done_gen()

    return StreamingResponse(gen, media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
