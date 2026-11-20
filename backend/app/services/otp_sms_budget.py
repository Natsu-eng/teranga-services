"""Plafond GLOBAL des SMS de code réellement envoyés (DEPLOYMENT.md §18).

Les limites par numéro et par IP ne bornent pas un abus RÉPARTI sur beaucoup
de numéros et d'adresses : sans plafond, le coût SMS n'aurait pas de
maximum. Ce module en impose un, par heure et par 24 h glissantes, partagé
par toutes les instances (même stockage que les autres limites,
`app.services.rate_limit`).

- Compté seulement pour un SMS qui PART : les numéros du mode test (staging)
  n'en consomment pas.
- Au plafond : `request-otp` est refusé clairement (`EnvoiCodesSatureError`,
  503) ; une session déjà ouverte n'est jamais touchée (le rafraîchissement
  de jeton ne passe pas par ici).
- Alertes admin (best-effort, par l'appelant) quand l'usage journalier
  atteint OTP_SMS_ALERT_THRESHOLD_PERCENT puis 100 % du plafond, UNE SEULE
  fois par fenêtre : un verrou à usage unique (`max_hits=1` sur la fenêtre
  journalière) dans le même stockage partagé le garantit, même avec
  plusieurs instances.

Aucun compteur n'est lu directement : le contrat `RateLimiter` ne fait
qu'enregistrer et refuser. Un seuil est détecté par un compteur parallèle
plafonné à `seuil - 1` : son premier refus marque l'envoi qui ATTEINT le
seuil.
"""

import math
from dataclasses import dataclass
from enum import StrEnum

from app.core.config import Settings
from app.core.errors import AppError
from app.services.rate_limit import RateLimiter

# Clés du compteur global (un seul compteur pour toute la plateforme).
_HOUR_KEY = "global:hour"
_DAY_KEY = "global:day"
_THRESHOLD_KEY = "global:day:threshold"
_FULL_KEY = "global:day:full"
_THRESHOLD_LATCH = "alert:threshold"
_FULL_LATCH = "alert:full"


class SmsBudgetAlert(StrEnum):
    # Seuil d'alerte (OTP_SMS_ALERT_THRESHOLD_PERCENT) du plafond journalier atteint.
    THRESHOLD = "threshold"
    # Plafond journalier atteint : les envois suivants seront refusés.
    FULL = "full"


@dataclass(frozen=True)
class SmsBudgetDecision:
    allowed: bool
    # Alerte à envoyer aux admins APRÈS la réponse (au plus une par appel).
    alert: SmsBudgetAlert | None


class EnvoiCodesSatureError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="ENVOI_CODES_SATURE",
            message=(
                "Trop de codes de connexion ont été envoyés ces dernières heures. "
                "Réessayez un peu plus tard. Si vous êtes déjà connecté, rien ne change "
                "pour vous."
            ),
            status_code=503,
        )


def alert_threshold(settings: Settings) -> int:
    """Nombre de SMS sur 24 h qui déclenche l'alerte intermédiaire."""
    return max(
        1,
        math.ceil(
            settings.otp_sms_global_max_per_day * settings.otp_sms_alert_threshold_percent / 100
        ),
    )


async def _reaches(limiter: RateLimiter, key: str, threshold: int, window_seconds: int) -> bool:
    """Vrai pour l'envoi qui ATTEINT `threshold` (et les suivants). Compteur
    plafonné à `threshold - 1` : il accepte les `threshold - 1` premiers
    envois, puis refuse -- le premier refus est l'envoi n° `threshold`."""
    if threshold <= 1:
        return True
    return not await limiter.check(key, max_hits=threshold - 1, window_seconds=window_seconds)


async def _first_time(limiter: RateLimiter, latch: str, window_seconds: int) -> bool:
    """Verrou à usage unique par fenêtre : vrai la première fois seulement."""
    return await limiter.check(latch, max_hits=1, window_seconds=window_seconds)


async def reserve_sms(limiter: RateLimiter, settings: Settings) -> SmsBudgetDecision:
    """Réserve UN envoi de SMS dans le plafond global, ou le refuse.

    Ordre : heure puis jour. Un refus horaire ne consomme pas le budget
    journalier (un pic ne fait pas atteindre le plafond du jour plus tôt).
    """
    day_window = settings.otp_sms_global_day_window_seconds
    if not await limiter.check(
        _HOUR_KEY,
        max_hits=settings.otp_sms_global_max_per_hour,
        window_seconds=settings.otp_sms_global_hour_window_seconds,
    ):
        return SmsBudgetDecision(allowed=False, alert=None)
    day_max = settings.otp_sms_global_max_per_day
    if not await limiter.check(_DAY_KEY, max_hits=day_max, window_seconds=day_window):
        # Déjà au plafond : l'alerte « plafond » a normalement été envoyée par
        # l'envoi qui l'a atteint ; le verrou évite tout doublon.
        full = await _first_time(limiter, _FULL_LATCH, day_window)
        return SmsBudgetDecision(allowed=False, alert=SmsBudgetAlert.FULL if full else None)

    alert: SmsBudgetAlert | None = None
    if await _reaches(limiter, _FULL_KEY, day_max, day_window):
        # Cet envoi atteint le plafond : alerte « plafond », une fois.
        alert = SmsBudgetAlert.FULL if await _first_time(limiter, _FULL_LATCH, day_window) else None
    elif await _reaches(
        limiter, _THRESHOLD_KEY, alert_threshold(settings), day_window
    ) and await _first_time(limiter, _THRESHOLD_LATCH, day_window):
        alert = SmsBudgetAlert.THRESHOLD
    return SmsBudgetDecision(allowed=True, alert=alert)
