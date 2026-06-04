import operator
from dataclasses import dataclass, field
from typing import Optional
from typing_extensions import Annotated

from shared.models import ClarifiedContext, Expert, ResearchResult


@dataclass(kw_only=True)
class ResearchState:
    # ── Phase 0 : Clarification ──────────────────────────────────────────────
    raw_request: str = field(default="")
    clarification_messages: Annotated[list, operator.add] = field(default_factory=list)
    clarification_complete: bool = field(default=False)
    clarified_context: Optional[ClarifiedContext] = field(default=None)

    # ── Phase 1 : Équipe d'experts ───────────────────────────────────────────
    expert_team: list = field(default_factory=list)   # list[Expert]
    team_validated: bool = field(default=False)

    # ── Phase 2 : Résultats de recherche ────────────────────────────────────
    # Annotated list so fan-out results accumulate via operator.add
    expert_results: Annotated[list, operator.add] = field(default_factory=list)
    joker_report: str = field(default="")

    # ── Phase 3a : Vision ────────────────────────────────────────────────────
    vision_summary: str = field(default="")
    vision_validated: bool = field(default=False)
    vision_feedback: str = field(default="")

    # ── Phase 3b : Rapport final ─────────────────────────────────────────────
    final_report: str = field(default="")


@dataclass(kw_only=True)
class ResearchStateInput:
    raw_request: str = field(default="")


@dataclass(kw_only=True)
class ResearchStateOutput:
    final_report: str = field(default="")
    vision_summary: str = field(default="")
