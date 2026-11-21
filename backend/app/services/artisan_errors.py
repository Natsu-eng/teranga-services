"""Erreurs métier des artisans (BUILD_PLAN.md §3.2) : paramètres de
recherche invalides, page hors bornes, artisan ou métier introuvable,
statistiques privées, métier déjà déclaré, zone d'intervention invalide.
Extraites de `app.services.artisans` ; codes, messages et statuts HTTP
inchangés.
"""

from app.core.errors import AppError


class PositionInvalideError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="POSITION_INVALIDE",
            message="La position fournie (near) est invalide. Format attendu : lat,lng.",
            status_code=422,
        )


class RayonRechercheInvalideError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="RAYON_RECHERCHE_INVALIDE",
            message="Le rayon de recherche demandé est invalide ou dépasse le maximum autorisé.",
            status_code=422,
        )


class TriDistanceSansPositionError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="TRI_DISTANCE_SANS_POSITION",
            message="Le tri par distance (sort=distance) nécessite une position (near).",
            status_code=422,
        )


class PageHorsBornesError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="PAGE_HORS_BORNES",
            message="Le numéro de page demandé dépasse le maximum autorisé.",
            status_code=422,
        )


class ArtisanIntrouvableError(AppError):
    def __init__(self) -> None:
        super().__init__(code="ARTISAN_NOT_FOUND", message="Artisan introuvable.", status_code=404)


class StatistiquesPriveesInterditesError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="STATISTIQUES_PRIVEES_INTERDITES",
            message="Vous n'avez pas accès aux statistiques financières de cet artisan.",
            status_code=403,
        )


class ArtisanProfilIntrouvableError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="ARTISAN_PROFIL_INTROUVABLE",
            message="Aucun profil artisan n'est associé à ce compte.",
            status_code=404,
        )


class MetierIntrouvableError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="METIER_INTROUVABLE",
            message="Ce métier n'existe pas ou n'est plus actif.",
            status_code=422,
        )


class ArtisanMetierDejaDeclareError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="ARTISAN_METIER_DEJA_DECLARE",
            message="Vous exercez déjà ce métier -- retirez-le d'abord pour en changer les"
            " conditions.",
            status_code=409,
        )


class ArtisanTradeIntrouvableError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="ARTISAN_TRADE_NOT_FOUND",
            message="Ce métier déclaré est introuvable.",
            status_code=404,
        )


class ZoneInterventionInvalideError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="ZONE_INTERVENTION_INVALIDE",
            message="La zone d'intervention fournie est invalide (le polygone doit être fermé).",
            status_code=422,
        )


class FormatPositionObsoleteError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="FORMAT_POSITION_OBSOLETE",
            message="Ce format de position (base_location, coordonnées libres) n'est plus"
            ' accepté. Envoyez location = {"source": "neighborhood", "neighborhood_id": ...}'
            ' ou {"source": "gps", "lat": ..., "lng": ...}.',
            status_code=422,
        )


class QuartierInconnuError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="QUARTIER_INCONNU",
            message="Ce quartier ne fait pas partie des quartiers desservis.",
            status_code=422,
        )


class HorsRegionDesservieError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="HORS_REGION_DESSERVIE",
            message="Cette position est en dehors de la région desservie par Téranga."
            " Choisissez plutôt votre quartier.",
            status_code=422,
        )


class RayonInterventionTropGrandError(AppError):
    def __init__(self, max_m: int) -> None:
        super().__init__(
            code="RAYON_INTERVENTION_TROP_GRAND",
            message=f"Le rayon d'intervention ne peut pas dépasser {max_m // 1000} km.",
            status_code=422,
        )


class TropDeChangementsDeZoneError(AppError):
    def __init__(self, *, max_changes: int, window_label: str, retry_at_label: str) -> None:
        super().__init__(
            code="TROP_DE_CHANGEMENTS_DE_ZONE",
            message=f"Vous avez déjà changé votre zone d'intervention {max_changes} fois"
            f" en {window_label}. Prochain changement possible le {retry_at_label}.",
            status_code=429,
        )
