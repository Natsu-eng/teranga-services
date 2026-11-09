"""Livraison des codes OTP, derrière une interface indépendante du fournisseur.

Le fournisseur actif est choisi par configuration (`SMS_PROVIDER`), jamais
codé en dur -- voir `get_sms_provider` : `console` (dev), `termii` (envoi
réel, app/services/sms_termii.py) ou `unconfigured` (échoue explicitement).
Le fournisseur ne fait que LIVRER : génération, hachage et vérification du
code restent dans app/services/otp.py.
"""

import logging
from typing import Protocol

from app.core.config import Settings, get_settings
from app.core.errors import AppError

logger = logging.getLogger(__name__)


class OtpEnvoiIndisponibleError(AppError):
    """Le fournisseur n'a pas pu livrer le code (panne, refus, délai).

    Erreur APPLICATIVE (503) : convertie en réponse JSON à l'intérieur de la
    pile de middlewares, donc avec les en-têtes CORS -- le front affiche ce
    message au lieu d'un faux « Impossible de contacter le serveur ». La
    cause est journalisée côté serveur, jamais renvoyée au client.
    """

    def __init__(self) -> None:
        super().__init__(
            code="OTP_ENVOI_INDISPONIBLE",
            message=(
                "L'envoi du code de connexion a échoué, merci de réessayer dans quelques instants."
            ),
            status_code=503,
        )


class SmsProvider(Protocol):
    async def send_otp(self, phone: str, code: str) -> None:
        """Envoie le code OTP au numéro E.164 donné."""
        ...


class ConsoleSmsProvider:
    """Provider de dev : journalise le code au lieu d'envoyer un vrai SMS.

    Le code n'est écrit en clair dans les logs qu'en development/test --
    vérifié ici même (et pas seulement au choix du provider) pour qu'un
    mauvais branchage en staging/prod ne fasse jamais fuiter un code OTP.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    async def send_otp(self, phone: str, code: str) -> None:
        if self._settings.is_local:
            logger.info("[dev] Code OTP pour %s : %s", phone, code)
        else:
            logger.warning(
                "ConsoleSmsProvider utilisé hors poste de développement (ENVIRONMENT=%s) -- "
                "code OTP volontairement non journalisé.",
                self._settings.environment,
            )


class UnconfiguredSmsProvider:
    """Squelette pour un fournisseur SMS réel, à choisir avant la mise en production."""

    async def send_otp(self, phone: str, code: str) -> None:
        raise NotImplementedError(
            "Aucun fournisseur SMS réel n'est configuré (SMS_PROVIDER=unconfigured). "
            "Choisissez et implémentez un provider (voir app/services/sms.py) avant la prod."
        )


def get_sms_provider(settings: Settings | None = None) -> SmsProvider:
    settings = settings or get_settings()
    if settings.sms_provider == "console":
        return ConsoleSmsProvider(settings)
    if settings.sms_provider == "termii":
        # Import tardif : httpx et le module Termii ne sont chargés que si
        # ce fournisseur est choisi.
        from app.services.sms_termii import TermiiSmsProvider

        return TermiiSmsProvider(settings)
    return UnconfiguredSmsProvider()
