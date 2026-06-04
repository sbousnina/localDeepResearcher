# Architecture Multi-Agent Expert Team

## Vue d'ensemble

La version 2.0 transforme le deep researcher séquentiel en un système multi-agents parallèles structuré comme une équipe d'experts en entreprise. Le but principal est de réduire l'overthinking et l'éparpillement en imposant une clarification du besoin, une validation progressive, et un output orienté décision.

## Flux de conversation

```
CLARIFYING ──► TEAM_PROPOSAL ──► TEAM_ADJUSTING
                    │
                    ▼ (validation OK)
               EXECUTING
                    │
                    ▼
               VISION_PROPOSAL ──► VISION_ADJUSTING
                    │
                    ▼ (validation OK)
               DETAIL_EXECUTING
                    │
                    ▼
                  DONE
```

## Phases et checkpoints

### Phase 0 — Clarification (Grill-Me)

L'agent clarification pose des questions adaptatives sans limite fixe jusqu'à avoir une confiance ≥ 0.85 sur les 5 axes :

1. **Situation** : contexte actuel, rôle, environnement
2. **Objectif** : ce que l'utilisateur veut vraiment accomplir
3. **Succès** : définition concrète et mesurable à 30/90 jours
4. **Contraintes** : temps, budget, énergie, équipe, compétences
5. **Bloqueur** : plus grand obstacle ou peur

**Checkpoint 1** : résumé structuré présenté → confirmation avant de continuer.

### Phase 1 — Assemblage équipe

Le PM détecte et propose 2-3 experts avec :
- Nom et rôle précis
- Méthodologie explicite (LEAN, 5 Pourquoi, First Principles, SWOT, ADKAR, Blue Ocean, etc.)
- Angle de recherche spécifique (une question, pas un domaine vague)

**Checkpoint 2** : l'utilisateur valide ou ajuste la composition de l'équipe.

### Phase 2 — Recherche parallèle

Chaque expert tourne simultanément via `asyncio.gather()` en invoquant le research sub-graph existant avec son propre persona et topic. Puis l'**Agent Joker (Red Team)** tourne séquentiellement pour :
- Identifier contradictions entre experts
- Challenger hypothèses implicites
- Révéler angles morts
- Produire un scénario pessimiste

### Phase 3a — Vision stratégique

Le Chief of Staff distille **3-5 bullets MAX** de direction stratégique.

**Checkpoint 3** : l'utilisateur valide la direction avant l'investissement dans le détail.

### Phase 3b — Rapport détaillé

Seulement après validation de la vision, le rapport complet est généré :

```
## 🎯 Vision Validée
## 👥 Perspectives Expertes (par agent)
## 🃏 Points de Vigilance (Red Team)
## ✅ Call-to-Actions Priorisés
   🔴 Cette semaine | 🟡 Ce mois | 🟢 Backlog
## 🗓 Roadmap 30/60/90 jours
## ⛔ Ne pas faire / Éviter  [obligatoire — anti-éparpillement]
## 📚 Sources consolidées
```

## Structure des modules

```
src/
├── shared/                    # Utilitaires purs, zéro dépendance métier
│   ├── models.py              # Expert, ClarifiedContext, ResearchResult (Pydantic)
│   ├── sse.py                 # make_chunk(), done_chunk() — source unique
│   └── validation.py          # detect_validation_intent(), detect_adjustment_intent()
│
├── ollama_deep_researcher/    # Research sub-graph — inchangé (réutilisé)
│   ├── graph.py               # Boucle: generate_query → web_research → summarize → reflect
│   ├── state.py               # SummaryState
│   ├── prompts.py             # Prompts de recherche
│   ├── configuration.py       # Config + 3 nouveaux champs
│   └── utils.py               # Search APIs (searxng, duckduckgo, tavily, perplexity)
│
├── agents/                    # Un concern par fichier
│   ├── clarification.py       # Interviewer multi-tour adaptatif
│   ├── team_assembly.py       # Proposer + validator d'équipe
│   ├── expert_runner.py       # Fan-out wrapper autour du sub-graph
│   ├── joker.py               # Red Team / Devil's Advocate
│   └── synthesizer.py         # vision_synthesis() + detail_synthesis()
│
├── supervisor/                # Orchestrateur multi-agent
│   ├── state.py               # ResearchState multi-phase
│   ├── prompts.py             # Tous les prompts nouveaux
│   └── graph.py               # LangGraph supervisor (extract → team → experts → joker)
│
└── api.py                     # Couche routing mince — machine d'état ConvState
```

## Encodage d'état dans les messages

L'état est encodé dans les messages assistant via des marqueurs HTML invisibles :

| Marqueur | Signification |
|----------|---------------|
| `<!-- STATE:CLARIFICATION_DONE -->` | Clarification complète |
| `<!-- STATE:TEAM_PROPOSED -->` | Équipe proposée |
| `<!-- STATE:VISION_PROPOSED -->` | Vision stratégique présentée |
| `<!-- STATE:DETAIL_DONE -->` | Rapport final généré |
| `<!-- CONTEXT_JSON:...-->` | ClarifiedContext sérialisé |
| `<!-- RESULTS_JSON:...-->` | Expert results sérialisés |
| `<!-- JOKER_JSON:...-->` | Rapport Red Team |
| `<!-- VISION_TEXT:...-->` | Texte de la vision validée |

Cette approche préserve la compatibilité OpenAI (pas de champs supplémentaires dans l'API) et permet la reconstruction complète de l'état à partir de l'historique de conversation.

## Nouveaux champs de configuration

| Variable | Défaut | Description |
|----------|--------|-------------|
| `MAX_EXPERTS` | `3` | Nombre max d'experts parallèles |
| `ENABLE_JOKER` | `true` | Active l'agent Red Team |
| `ENABLE_SYNTHESIS` | `true` | Active la synthèse en deux phases |

Tous les champs existants restent compatibles.

## Mode direct (bypass)

Les préfixes `!fast` ou `/direct` bypasse les phases 0, 1, 3a et lance directement la recherche avec un expert généraliste :

```
!fast analyse le marché de l'IA en santé
/direct quelles sont les meilleures pratiques LEAN pour une startup
```

## Compatibilité Open WebUI

- Endpoint `/v1/chat/completions` : inchangé, OpenAI-compatible
- Streaming SSE : actif sur tous les états
- `/v1/models` : mêmes IDs de modèles
- CORS : inchangé (allow all origins)
