"""Envoi de SMS, derrière une interface indépendante du fournisseur.

Le fournisseur actif est choisi par configuration (`SMS_PROVIDER`), jamais
codé en dur -- voir `get_sms_provider`. Aucun fournisseur commercial n'est
branché à ce stade (BUILD_PLAN.md §4) : `UnconfiguredSmsProvider` est le
squelette qui échoue explicitement tant que ce choix n'est pas fait.
"""

import logging
from typing import Protocol

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


class SmsProvider(Protocol):
    async def send_otp(self, phone: str, code: str) -> None:
        """Envoie le code OTP au numéro E.164 donné."""
        ...


class ConsoleSmsProvider:
    """Provider de dev : journalise le code au lieu d'envoyer un vrai SMS.

    Le code n'est écrit en clair dans les logs que si `APP_ENV=dev` --
    vérifié ici même (et pas seulement au choix du provider) pour qu'un
    mauvais branchage en staging/prod ne fasse jamais fuiter un code OTP.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    async def send_otp(self, phone: str, code: str) -> None:
        if self._settings.app_env == "dev":
            logger.info("[dev] Code OTP pour %s : %s", phone, code)
        else:
            logger.warning(
                "ConsoleSmsProvider utilisé hors environnement dev (APP_ENV=%s) -- "
                "code OTP volontairement non journalisé.",
                self._settings.app_env,
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
    return UnconfiguredSmsProvider()
