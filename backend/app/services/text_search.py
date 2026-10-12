"""Recherche textuelle sûre pour les filtres `ILIKE`."""

# Caractère d'échappement des motifs LIKE (à passer en `escape=`).
LIKE_ESCAPE = "\\"


def contains_pattern(term: str) -> str:
    """Motif « contient `term` » où `%` et `_` saisis sont cherchés
    littéralement, jamais comme jokers."""
    escaped = (
        term.replace(LIKE_ESCAPE, LIKE_ESCAPE * 2)
        .replace("%", LIKE_ESCAPE + "%")
        .replace("_", LIKE_ESCAPE + "_")
    )
    return f"%{escaped}%"
