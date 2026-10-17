"""Erreurs métier de la messagerie (BUILD_PLAN.md §3.4) : accès refusé,
fil fermé, message vide ou trop long, curseurs incompatibles, pièce jointe
invalide ou introuvable. Extraites de `app.services.conversations` ; codes,
messages et statuts HTTP inchangés.
"""

from app.core.errors import AppError


class ConversationAccesInterditError(AppError):
    """Même réponse pour « n'existe pas » et « pas participant » : rien ne
    permet à un tiers de deviner qu'un fil existe."""

    def __init__(self) -> None:
        super().__init__(
            code="CONVERSATION_ACCES_INTERDIT",
            message="Vous n'avez pas accès à cette conversation.",
            status_code=403,
        )


class ConversationFermeeError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="CONVERSATION_FERMEE",
            message=(
                "Cette mise en relation a été refusée : la conversation n'accepte plus "
                "de nouveaux messages."
            ),
            status_code=409,
        )


class MessageVideError(AppError):
    def __init__(self) -> None:
        super().__init__(code="MESSAGE_VIDE", message="Le message est vide.", status_code=422)


class MessageTropLongError(AppError):
    def __init__(self, max_length: int) -> None:
        super().__init__(
            code="MESSAGE_TROP_LONG",
            message=f"Le message dépasse la longueur maximale ({max_length} caractères).",
            status_code=422,
        )


class CurseursIncompatiblesError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="CURSEURS_INCOMPATIBLES",
            message="Les paramètres « before » et « since » ne peuvent pas être combinés.",
            status_code=422,
        )


class PieceJointeVideError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="PIECE_JOINTE_VIDE", message="Le fichier envoyé est vide.", status_code=422
        )


class PieceJointeTypeInvalideError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="PIECE_JOINTE_TYPE_INVALIDE",
            message="Seules les photos JPEG ou PNG peuvent être envoyées (vérifié par leur "
            "contenu, pas par leur nom).",
            status_code=422,
        )


class PieceJointeTropVolumineuseError(AppError):
    def __init__(self, max_bytes: int) -> None:
        max_mo = max_bytes // (1024 * 1024)
        super().__init__(
            code="PIECE_JOINTE_TROP_VOLUMINEUSE",
            message=f"La photo dépasse la taille maximale autorisée ({max_mo} Mo).",
            status_code=413,
        )


class PieceJointeDimensionsExcessivesError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="PIECE_JOINTE_DIMENSIONS_EXCESSIVES",
            message="Les dimensions de cette photo sont trop grandes.",
            status_code=422,
        )


class PieceJointeIntrouvableError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="PIECE_JOINTE_INTROUVABLE",
            message="Cette pièce jointe est introuvable.",
            status_code=404,
        )
