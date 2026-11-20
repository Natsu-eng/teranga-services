"""Notifications e-mail des administrateurs (flux « push »).

`notify_verification_submitted` : un artisan vient de COMPLÉTER son dossier
de vérification (passage à « en attente de revue », voir
`app.services.verification.is_awaiting_review`) -- un e-mail par passage,
jamais un par document.

`notify_dispute_opened` : un client ou un artisan vient de signaler un
problème sur une intervention (litige, `app.services.disputes`) -- un
e-mail par litige (il n'y en a qu'un par intervention). Jamais le motif :
il peut contenir des détails personnels ; l'admin le lit dans le back-office.

`notify_support_ticket_created` : nouvelle demande d'aide
(`app.services.support`) -- la catégorie et le rôle de l'auteur seulement,
jamais le message.

**Best-effort, toujours** : appelée APRÈS la validation de l'envoi de
l'artisan (tâche d'arrière-plan), elle ne lève jamais d'exception -- un
échec d'e-mail est journalisé, l'envoi des documents reste réussi.

**Aucune fuite** : pas de pièce jointe, pas de document, pas de numéro de
téléphone ; au plus le nom affiché de l'artisan (vérification) ou le métier
et le rôle de qui a signalé (litige), et le lien vers la file d'attente du
back-office (l'admin s'y authentifie pour voir le dossier).
"""

import logging
import re

from app.core.config import Settings
from app.models.enums import Role, SupportCategory
from app.services.email import EmailProvider, EmailSendError, OutgoingEmail, get_email_provider

logger = logging.getLogger(__name__)

VERIFICATION_SUBJECT = "Téranga : documents de vérification à examiner"
ADMIN_VERIFICATIONS_PATH = "/admin/verifications"
DISPUTE_SUBJECT = "Téranga : un litige est à examiner"
ADMIN_DISPUTES_PATH = "/admin/litiges"
_REPORTER_LABELS = {Role.CLIENT: "le client", Role.ARTISAN: "l'artisan"}
SUPPORT_SUBJECT = "Téranga : nouvelle demande d'aide"
ADMIN_SUPPORT_PATH = "/admin/support"
_SUPPORT_AUTHOR_LABELS = {Role.CLIENT: "un client", Role.ARTISAN: "un artisan"}
_SUPPORT_CATEGORY_LABELS = {
    SupportCategory.COMPTE: "Compte",
    SupportCategory.UTILISATEUR: "Un artisan ou un client",
    SupportCategory.PAIEMENT: "Paiement",
    SupportCategory.BUG: "Problème technique",
    SupportCategory.AUTRE: "Autre",
}
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


def build_dispute_opened_email(
    trade_label: str, opened_by: Role, settings: Settings
) -> OutgoingEmail:
    """Métier, qui a signalé et le lien de la file : ni motif, ni nom, ni numéro."""
    link = settings.frontend_public_base_url.rstrip("/") + ADMIN_DISPUTES_PATH
    trade = " ".join(trade_label.split()) or "non précisé"
    reporter = _REPORTER_LABELS.get(opened_by, "une partie")
    lines = [
        "Bonjour,",
        "",
        "Un problème vient d'être signalé sur une intervention Téranga.",
        f"Métier : {trade}",
        f"Signalé par : {reporter}",
        "",
        f"Pour l'examiner et trancher : {link}",
        "",
        "— Téranga",
    ]
    return OutgoingEmail(
        to=tuple(settings.admin_notification_emails),
        subject=DISPUTE_SUBJECT,
        body="\n".join(lines),
    )


async def notify_dispute_opened(
    trade_label: str,
    opened_by: Role,
    settings: Settings,
    *,
    provider: EmailProvider | None = None,
) -> None:
    """Prévient les admins d'un nouveau litige ; n'échoue JAMAIS."""
    if not settings.admin_notification_emails:
        logger.info("Litige ouvert : aucun destinataire configuré.")
        return
    try:
        email = build_dispute_opened_email(trade_label, opened_by, settings)
        await (provider or get_email_provider(settings)).send(email)
    except Exception as exc:  # best-effort : rien ne doit remonter à la partie
        detail = exc.safe_detail if isinstance(exc, EmailSendError) else type(exc).__name__
        logger.error("Notification admin (litige ouvert) NON envoyée : %s.", detail)
        return
    logger.info(
        "Notification admin envoyée (litige ouvert) à %d destinataire(s).",
        len(settings.admin_notification_emails),
    )


def build_support_ticket_email(
    category: SupportCategory, author_role: Role, settings: Settings
) -> OutgoingEmail:
    """Catégorie, rôle de l'auteur et lien de la file : ni message, ni nom,
    ni numéro."""
    link = settings.frontend_public_base_url.rstrip("/") + ADMIN_SUPPORT_PATH
    lines = [
        "Bonjour,",
        "",
        "Une nouvelle demande d'aide est arrivée sur Téranga.",
        f"Catégorie : {_SUPPORT_CATEGORY_LABELS.get(category, 'Autre')}",
        f"Envoyée par : {_SUPPORT_AUTHOR_LABELS.get(author_role, 'un utilisateur')}",
        "",
        f"Pour la lire et y répondre : {link}",
        "",
        "— Téranga",
    ]
    return OutgoingEmail(
        to=tuple(settings.admin_notification_emails),
        subject=SUPPORT_SUBJECT,
        body="\n".join(lines),
    )


async def notify_support_ticket_created(
    category: SupportCategory,
    author_role: Role,
    settings: Settings,
    *,
    provider: EmailProvider | None = None,
) -> None:
    """Prévient les admins d'une nouvelle demande d'aide ; n'échoue JAMAIS."""
    if not settings.admin_notification_emails:
        logger.info("Demande d'aide : aucun destinataire configuré.")
        return
    try:
        email = build_support_ticket_email(category, author_role, settings)
        await (provider or get_email_provider(settings)).send(email)
    except Exception as exc:  # best-effort : rien ne doit remonter à l'auteur
        detail = exc.safe_detail if isinstance(exc, EmailSendError) else type(exc).__name__
        logger.error("Notification admin (demande d'aide) NON envoyée : %s.", detail)
        return
    logger.info(
        "Notification admin envoyée (demande d'aide) à %d destinataire(s).",
        len(settings.admin_notification_emails),
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
