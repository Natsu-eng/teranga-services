"""Notifications e-mail des administrateurs (flux « push »).

`notify_verification_submitted` : un artisan vient de COMPLÉTER son dossier
de vérification (passage à « en attente de revue », voir
`app.services.verification.is_awaiting_review`) -- un e-mail par passage,
jamais un par document.

**Best-effort, toujours** : appelée APRÈS la validation de l'envoi de
l'artisan (tâche d'arrière-plan), elle ne lève jamais d'exception -- un
échec d'e-mail est journalisé, l'envoi des documents reste réussi.

**Aucune fuite** : pas de pièce jointe, pas de document, pas de numéro de
téléphone ; au plus le nom affiché de l'artisan, et le lien vers la file
d'attente du back-office (l'admin s'y authentifie pour voir le dossier).
"""

import logging
import re

from app.core.config import Settings
from app.services.email import EmailProvider, EmailSendError, OutgoingEmail, get_email_provider

logger = logging.getLogger(__name__)

VERIFICATION_SUBJECT = "Téranga : documents de vérification à examiner"
ADMIN_VERIFICATIONS_PATH = "/admin/verifications"
# Nom « affichable » : un ancien compte peut avoir son numéro de téléphone
# comme nom (avant le correctif de confidentialité) -- jamais envoyé par e-mail.
_PHONE_LIKE_RE = re.compile(r"[+()0-9 .-]+")


def _display_name(full_name: str | None) -> str | None:
    """Nom sur une ligne, ou None s'il est vide ou ressemble à un numéro."""
    if not full_name:
        return None
    name = " ".join(full_name.split())  # aucun retour à la ligne, espaces normalisés
    if not name or _PHONE_LIKE_RE.fullmatch(name):
        return None
    return name


def build_verification_submitted_email(
    artisan_name: str | None, settings: Settings
) -> OutgoingEmail:
    link = settings.frontend_public_base_url.rstrip("/") + ADMIN_VERIFICATIONS_PATH
    name = _display_name(artisan_name)
    lines = ["Bonjour,", "", "Un artisan a soumis ses documents de vérification sur Téranga."]
    if name is not None:
        lines.append(f"Artisan : {name}")
    lines += ["", f"Pour les examiner : {link}", "", "— Téranga"]
    return OutgoingEmail(
        to=tuple(settings.admin_notification_emails),
        subject=VERIFICATION_SUBJECT,
        body="\n".join(lines),
    )


async def notify_verification_submitted(
    artisan_name: str | None,
    settings: Settings,
    *,
    provider: EmailProvider | None = None,
) -> None:
    """Prévient les admins ; n'échoue JAMAIS (best-effort, journalisé)."""
    if not settings.admin_notification_emails:
        logger.info("Dossier de vérification soumis : aucun destinataire configuré.")
        return
    try:
        email = build_verification_submitted_email(artisan_name, settings)
        await (provider or get_email_provider(settings)).send(email)
    except Exception as exc:  # best-effort : rien ne doit remonter à l'artisan
        # Détail SÛR seulement : statut et code du fournisseur (refus Brevo),
        # sinon le type de l'erreur (réseau, SMTP...) -- jamais son message,
        # qui peut citer des adresses ou des détails du serveur.
        detail = exc.safe_detail if isinstance(exc, EmailSendError) else type(exc).__name__
        logger.error("Notification admin (dossier de vérification) NON envoyée : %s.", detail)
        return
    logger.info(
        "Notification admin envoyée (dossier de vérification soumis) à %d destinataire(s).",
        len(settings.admin_notification_emails),
    )
