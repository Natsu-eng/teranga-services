"""Détection du type réel d'un fichier par ses en-têtes binaires (« magic
bytes »), jamais par son extension ni son `Content-Type` déclaré -- les deux
se falsifient trivialement (renommer un `.exe` en `.jpg`, mentir dans le
header HTTP). Utilisé par `app.services.documents` pour l'upload de
documents de vérification (BUILD_PLAN.md, onboarding artisan).

Volontairement sans dépendance externe (pas de `python-magic`, qui lie la
libmagic système -- absente par défaut sur Windows, contrainte de
déploiement inutile) : les signatures suffisantes pour les formats
réellement acceptés (JPEG, PNG, PDF) tiennent en quelques octets.
"""

from enum import StrEnum


class DetectedFileType(StrEnum):
    JPEG = "jpeg"
    PNG = "png"
    PDF = "pdf"


# Ordre sans importance : les signatures ne se chevauchent pas. Chaque
# signature est vérifiée par préfixe exact sur les octets de tête du fichier.
_SIGNATURES: tuple[tuple[bytes, DetectedFileType], ...] = (
    (b"\xff\xd8\xff", DetectedFileType.JPEG),
    (b"\x89PNG\r\n\x1a\n", DetectedFileType.PNG),
    (b"%PDF-", DetectedFileType.PDF),
)

EXTENSION_BY_TYPE: dict[DetectedFileType, str] = {
    DetectedFileType.JPEG: "jpg",
    DetectedFileType.PNG: "png",
    DetectedFileType.PDF: "pdf",
}

MIME_BY_TYPE: dict[DetectedFileType, str] = {
    DetectedFileType.JPEG: "image/jpeg",
    DetectedFileType.PNG: "image/png",
    DetectedFileType.PDF: "application/pdf",
}


def detect_file_type(content: bytes) -> DetectedFileType | None:
    """Renvoie le type détecté depuis les octets de tête, ou `None` si aucune
    signature connue ne correspond (fichier rejeté par l'appelant)."""
    for signature, kind in _SIGNATURES:
        if content.startswith(signature):
            return kind
    return None
