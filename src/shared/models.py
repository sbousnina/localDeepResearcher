from pydantic import BaseModel, Field


class Expert(BaseModel):
    name: str = Field(description="Nom de l'expert (ex: Sophie Martin)")
    role: str = Field(description="Rôle / titre (ex: Stratège Innovation)")
    methodology: str = Field(description="Cadre méthodologique appliqué (ex: LEAN Startup, 5 Pourquoi)")
    research_angle: str = Field(description="Question spécifique à investiguer pour cet expert")


class ClarifiedContext(BaseModel):
    situation: str = Field(description="Situation actuelle de l'utilisateur")
    goal: str = Field(description="Objectif principal visé")
    success_criteria: str = Field(description="Définition du succès à 30/90 jours")
    constraints: str = Field(description="Contraintes : temps, budget, énergie, équipe")
    main_blocker: str = Field(description="Plus grand bloqueur ou peur")
    confidence_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Score de confiance du LLM sur sa compréhension du besoin (0-1)",
    )


class ResearchResult(BaseModel):
    expert_name: str
    expert_role: str
    methodology: str
    summary: str
    sources: list[str] = Field(default_factory=list)
    key_insights: list[str] = Field(default_factory=list)
