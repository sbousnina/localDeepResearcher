"""Centralised user-intent detection for conversation state transitions."""

# Tokens that signal the user approves / wants to proceed
_VALIDATION_TOKENS: frozenset[str] = frozenset({
    "ok", "go", "oui", "yes", "top", "parfait", "lancez", "valider",
    "allez", "start", "c'est bon", "go-go", "let's go", "letsgo",
    "proceed", "continuer", "continue", "confirmed", "confirme",
    "approuver", "approved", "done", "allons-y", "c est bon",
})

# Prefixes that also count as validation
_VALIDATION_PREFIXES: tuple[str, ...] = (
    "ok ", "go ", "oui ", "yes ", "top ", "parfait", "lancez",
    "valider", "confirme", "approuve",
)


def detect_validation_intent(msg: str) -> bool:
    """Return True if the message expresses approval / go-ahead intent."""
    cleaned = msg.strip().lower().rstrip("!.,;")
    if cleaned in _VALIDATION_TOKENS:
        return True
    for prefix in _VALIDATION_PREFIXES:
        if cleaned.startswith(prefix):
            return True
    return False


def detect_adjustment_intent(msg: str) -> bool:
    """Return True if the message requests a change (not a full validation)."""
    if detect_validation_intent(msg):
        return False
    triggers = [
        "ajoute", "enlève", "retire", "change", "modifie", "remplace",
        "swap", "add", "remove", "adjust", "update", "plutôt", "instead",
        "different", "autre", "autrement",
    ]
    lowered = msg.lower()
    return any(t in lowered for t in triggers)
