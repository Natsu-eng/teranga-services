"""Erreurs communes aux opérations sur une intervention (BUILD_PLAN.md §6
Lot 12, §3.5).

Module séparé de `app.services.interventions` pour que les paiements
(`app.services.payments`) puissent les lever sans dépendre du service des
interventions -- qui, lui, s'appuie sur les paiements (complétion,
annulation). Y figurent aussi les refus de création et d'annulation d'une
intervention (demande d'autrui, artisan inéligible, fonds en séquestre).
"""

from app.core.errors import AppError


class InterventionIntrouvableError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="INTERVENTION_NOT_FOUND", message="Intervention introuvable.", status_code=404
        )


class InterventionAccesInterditError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="INTERVENTION_ACCES_INTERDIT",
            message="Vous n'avez pas accès à cette intervention.",
            status_code=403,
        )


class InterventionTransitionInvalideError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="TRANSITION_INTERVENTION_INVALIDE",
            message="Cette action n'est pas possible dans l'état actuel de l'intervention.",
            status_code=409,
        )


class ActionReserveeAutrePartieError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="ACTION_RESERVEE_AUTRE_PARTIE",
            message="Cette action est réservée à l'autre partie de cette intervention.",
            status_code=403,
        )


class AnnulationFondsRetenusError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="ANNULATION_FONDS_RETENUS",
            message=(
                "Votre paiement est en séquestre : signalez un problème, un conseiller "
                "Téranga tranchera et vous serez remboursé si les travaux n'ont pas été faits."
            ),
            status_code=409,
        )


class DemandeAutruiInterditeError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="DEMANDE_AUTRUI_INTERDITE",
            message="Cette demande n'appartient pas au client courant.",
            status_code=403,
        )


class DemandeNonOuverteError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="DEMANDE_NON_OUVERTE",
            message="Cette demande n'est plus ouverte à une mise en relation.",
            status_code=409,
        )


class ArtisanNonVerifieError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="ARTISAN_NON_VERIFIE",
            message="Cet artisan n'est pas encore vérifié.",
            status_code=422,
        )


class ArtisanIndisponibleError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="ARTISAN_INDISPONIBLE",
            message="Cet artisan ne peut pas recevoir de nouvelles demandes pour le moment.",
            status_code=422,
        )


class ArtisanMetierNonExerceError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="ARTISAN_METIER_NON_EXERCE",
            message="Cet artisan n'exerce pas le métier demandé.",
            status_code=422,
        )


class ArtisanHorsZoneError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="ARTISAN_HORS_ZONE",
            message="Cet artisan ne couvre pas géographiquement cette demande.",
            status_code=422,
        )


class LitigeDelaiDepasseError(AppError):
    """Fin des travaux confirmée il y a plus de DISPUTE_WINDOW_HOURS (ou
    fenêtre désactivée) : le signalement n'est plus possible."""

    def __init__(self) -> None:
        super().__init__(
            code="LITIGE_DELAI_DEPASSE",
            message=("Le délai pour signaler un problème sur ces travaux est dépassé."),
            status_code=409,
        )


class LitigeDejaOuvertError(AppError):
    """Un seul litige par intervention, même tranché : pas de second recours."""

    def __init__(self) -> None:
        super().__init__(
            code="LITIGE_DEJA_OUVERT",
            message="Un problème a déjà été signalé sur cette intervention.",
            status_code=409,
        )


class LitigePaiementDejaVerseError(AppError):
    """Paiement en ligne déjà versé à l'artisan : Téranga ne détient plus les
    fonds, un litige ne pourrait rien geler (versement différé : à venir avec
    l'agrégateur)."""

    def __init__(self) -> None:
        super().__init__(
            code="LITIGE_PAIEMENT_DEJA_VERSE",
            message=(
                "Le paiement a déjà été versé à l'artisan : ce problème ne peut plus être "
                "signalé ici."
            ),
            status_code=409,
        )
