# Local Deep Researcher — Multi-Agent Expert Team

Système de recherche local multi-agents : clarifie ton besoin, assemble une équipe d'experts spécialisés, les fait travailler en parallèle avec un agent Red Team, et livre un rapport structuré avec des call-to-actions prioritaires.

```text
[Clarification]  →  [Équipe d'experts]  →  [Recherche parallèle]  →  [Red Team]  →  [Vision]  →  [Rapport]
```

---

## Démarrage rapide

### Prérequis

- Docker + Docker Compose
- Ollama qui tourne sur le réseau `infra-net` (`infra-ollama`)
- Open WebUI sur le même réseau (optionnel mais recommandé)

### Lancer les services

```bash
git clone https://github.com/sbousnina/localDeepResearcher.git
cd localDeepResearcher
docker-compose up -d --build
```

C'est tout. Trois services démarrent :

| Service | URL | Rôle |
|---------|-----|------|
| API multi-agent | `http://localhost:8086` | Endpoint OpenAI-compatible |
| SearXNG | `http://localhost:8888` | Moteur de recherche local |
| (Ollama + Open WebUI) | déjà sur `infra-net` | LLM + interface |

### Configurer Open WebUI

Dans Open WebUI → ⚙️ Admin Panel → Settings → Connections → OpenAI API :

- **URL** : `http://local-deep-researcher:8000/v1`
- **API Key** : `local` (n'importe quoi)

Puis sélectionne le modèle **`local-deep-researcher`** dans une nouvelle conversation.

---

## Utilisation

### Mode normal (recommandé)

Lance une conversation avec ta situation réelle. Le système va :

1. **Te poser des questions** pour clarifier ton besoin (autant que nécessaire)
2. **Proposer une équipe** de 2-3 experts avec leurs méthodologies → valide ou ajuste
3. **Lancer la recherche** en parallèle + agent Red Team
4. **Présenter une direction** (3-5 bullets) → valide avant le détail
5. **Livrer le rapport complet** : CATs priorisés, roadmap 30/60/90j, liste "ne pas faire"

Exemples de demandes :
```
Je viens de commencer un poste de Responsable Innovation, je suis dev AI de base. Par où commencer ?

J'ai une solution SaaS B2B, comment la vendre mieux ?

Comment structurer mon équipe pour passer de 2 à 8 devs ?
```

Réponds **`OK`** aux checkpoints pour valider et passer à l'étape suivante.
Pour ajuster : *"Remplace l'expert marketing par un expert RH"*

### Mode direct (sans clarification)

Préfixe ta demande avec `!fast` pour bypasser toutes les étapes et lancer la recherche immédiatement :

```
!fast meilleures pratiques architecture microservices 2025
!fast comment négocier une augmentation de salaire développeur
```

---

## Configuration

Les variables d'environnement sont dans `docker-compose.yml` :

| Variable | Défaut | Description |
|----------|--------|-------------|
| `LOCAL_LLM` | `qwen3:14b` | Modèle Ollama à utiliser |
| `OLLAMA_BASE_URL` | `http://infra-ollama:11434` | URL Ollama |
| `SEARCH_API` | `searxng` | Moteur de recherche (`searxng`, `duckduckgo`, `tavily`) |
| `MAX_WEB_RESEARCH_LOOPS` | `3` | Profondeur de recherche par expert |
| `MAX_EXPERTS` | `3` | Nombre max d'experts parallèles |
| `ENABLE_JOKER` | `true` | Active l'agent Red Team |

---

## Architecture

Voir [docs/multi-agent-architecture.md](docs/multi-agent-architecture.md) pour le détail technique complet.

```
src/
├── shared/          # Modèles Pydantic + SSE + détection validation
├── agents/          # clarification · team_assembly · expert_runner · joker · synthesizer
├── supervisor/      # Graph LangGraph + état multi-phase + prompts
└── ollama_deep_researcher/  # Boucle de recherche (sub-graph réutilisé)
```
