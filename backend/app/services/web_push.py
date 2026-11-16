"""Envoi des notifications Web Push (RFC 8030), via `pywebpush`.

- **Chiffrement de bout en bout** (RFC 8291, `aes128gcm`) avec les clés du
  navigateur abonné : le service de push (Google, Mozilla, Apple, Microsoft)
  transporte un contenu qu'il ne peut pas lire.
- **Authentification VAPID** (RFC 8292) : chaque envoi est signé par la clé
  privée du serveur ; le navigateur n'accepte que les envois signés par la
  clé avec laquelle il s'est abonné.
- **Aucune requête vers une adresse arbitraire** : l'adresse d'abonnement
  doit être en https:// vers un service de push autorisé
  (WEB_PUSH_ALLOWED_ENDPOINT_HOSTS), vérifiée à l'abonnement ET à l'envoi ;
  les redirections ne sont jamais suivies.
- **Résultat sans fuite** : seul un détail sûr (statut HTTP, type d'erreur)
  remonte -- jamais l'adresse d'abonnement (une URL de capacité), ni la
  réponse libre du service.

`pywebpush` est synchrone (`requests`) : l'envoi part dans un thread, la
boucle asynchrone n'est jamais bloquée, et chaque requête a un délai borné
(WEB_PUSH_TIMEOUT_SECONDS).
"""

import asyncio
import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol
from urllib.parse import urlsplit

import requests
from py_vapid import Vapid
from pywebpush import WebPushException, webpush

from app.core.config import Settings, has_hidden_characters

# Validité du jeton VAPID signé pour CHAQUE envoi (RFC 8292 : 24 h au plus).
# Une heure : accepté par tous les services de push, Apple compris.
VAPID_TOKEN_TTL_SECONDS = 3600
# Codes par lesquels le service de push déclare l'abonnement mort pour de
# bon (RFC 8030 §7.3 : 410 Gone ; 404 chez certains services) : supprimé.
GONE_STATUSES = frozenset({404, 410})


def is_allowed_push_endpoint(endpoint: str, allowed_hosts: list[str]) -> bool:
    """Vrai si `endpoint` est une URL https:// (port par défaut, sans
    identifiants) vers un hôte autorisé, en nom exact ou en suffixe."""
    if has_hidden_characters(endpoint):
        return False
    try:
        parts = urlsplit(endpoint)
        port = parts.port
    except ValueError:
        return False
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or port not in (None, 443) or parts.username or parts.password:
        return False
    return any(host == allowed or host.endswith("." + allowed) for allowed in allowed_hosts)


@dataclass(frozen=True)
class PushTarget:
    """Un appareil abonné : adresse du service de push et clés du navigateur."""

    endpoint: str
    p256dh: str
    auth: str


@dataclass(frozen=True)
class PushNotification:
    """Contenu affiché par le service worker (frontend/pwa/sw.js)."""

    title: str
    body: str
    # Chemin RELATIF de l'application à ouvrir au clic (même origine).
    url: str
    # Regroupe les notifications d'un même fil sur l'appareil.
    tag: str
    # En-tête `Topic` (RFC 8030 §5.4) : si l'appareil est hors ligne, une
    # notification en attente du même sujet est remplacée, pas empilée.
    topic: str

    def payload(self) -> bytes:
        return json.dumps(
            {"title": self.title, "body": self.body, "url": self.url, "tag": self.tag},
            ensure_ascii=False,
        ).encode("utf-8")


class PushOutcome(StrEnum):
    DELIVERED = "delivered"
    # Abonnement mort (404/410) : à supprimer.
    GONE = "gone"
    FAILED = "failed"


@dataclass(frozen=True)
class PushResult:
    outcome: PushOutcome
    # Détail SÛR, journalisable : statut HTTP ou type d'erreur.
    detail: str


class PushSender(Protocol):
    async def send(self, target: PushTarget, notification: PushNotification) -> PushResult:
        """Envoie à UN appareil ; ne lève jamais (le résultat dit tout)."""
        ...


def push_http_session() -> requests.Session:
    session = requests.Session()
    # Une redirection lève TooManyRedirects au lieu d'être suivie : la
    # requête ne part jamais ailleurs que vers l'hôte autorisé.
    session.max_redirects = 0
    return session


class WebPushSender:
    """Envoi réel par `pywebpush` (contrat `PushSender`)."""

    def __init__(
        self,
        settings: Settings,
        *,
        session_factory: Callable[[], requests.Session] = push_http_session,
    ) -> None:
        private_key, subject = settings.vapid_private_key, settings.vapid_subject
        # Défense en profondeur : déjà exigés au démarrage (validate_web_push).
        if not (settings.web_push_enabled and private_key and subject):
            raise ValueError("Web Push incomplet : voir WEB_PUSH_ENABLED et VAPID_*.")
        self._vapid = Vapid.from_raw(private_key.encode("ascii"))
        self._subject = subject
        self._ttl = settings.web_push_ttl_seconds
        self._timeout = settings.web_push_timeout_seconds
        self._allowed_hosts = settings.web_push_allowed_endpoint_hosts
        # Point d'injection des tests (faux service de push, aucun réseau).
        self._session_factory = session_factory

    def _send_blocking(self, target: PushTarget, notification: PushNotification) -> PushResult:
        if not is_allowed_push_endpoint(target.endpoint, self._allowed_hosts):
            # Hôte retiré de la liste depuis l'abonnement : aucune requête.
            return PushResult(PushOutcome.FAILED, "hôte non autorisé")
        session = self._session_factory()
        try:
            webpush(
                subscription_info={
                    "endpoint": target.endpoint,
                    "keys": {"p256dh": target.p256dh, "auth": target.auth},
                },
                data=notification.payload(),
                vapid_private_key=self._vapid,
                # Dictionnaire neuf à chaque envoi (pywebpush le complète :
                # `aud` = origine du service de push).
                vapid_claims={
                    "sub": self._subject,
                    "exp": int(time.time()) + VAPID_TOKEN_TTL_SECONDS,
                },
                content_encoding="aes128gcm",
                ttl=self._ttl,
                # Message d'une personne : livraison prioritaire sur mobile.
                headers={"Urgency": "high", "Topic": notification.topic},
                timeout=self._timeout,
                requests_session=session,
            )
        except WebPushException as exc:
            # `is not None` : une Response en erreur est « fausse » en booléen.
            status = exc.response.status_code if exc.response is not None else None
            if status in GONE_STATUSES:
                return PushResult(PushOutcome.GONE, f"HTTP {status}")
            return PushResult(
                PushOutcome.FAILED, f"HTTP {status}" if status else "WebPushException"
            )
        except Exception as exc:  # réseau, délai, redirection refusée, clé invalide...
            return PushResult(PushOutcome.FAILED, type(exc).__name__)
        finally:
            session.close()
        return PushResult(PushOutcome.DELIVERED, "ok")

    async def send(self, target: PushTarget, notification: PushNotification) -> PushResult:
        return await asyncio.to_thread(self._send_blocking, target, notification)
