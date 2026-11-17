"""Clés VAPID du Web Push (RFC 8292) : décodage, contrôles et génération.

Format retenu, celui de `web-push generate-vapid-keys` (outil de référence)
et du script `scripts/generate_vapid_keys.py` : base64url SANS remplissage.

- Clé publique : point P-256 NON compressé (65 octets, préfixe 0x04). C'est
  l'`applicationServerKey` remise au navigateur à l'abonnement : publique
  par nature.
- Clé privée : scalaire P-256 brut (32 octets). SECRET : signe chaque envoi
  (jeton VAPID) ; jamais journalisée, jamais affichée dans une erreur.

Les deux clés forment une PAIRE : un abonnement créé avec une clé publique
n'accepte que les envois signés par la clé privée correspondante. Une paire
incohérente ferait échouer tous les envois (403) : elle est refusée dès le
démarrage (`app.core.config`, `public_key_matches`).
"""

import base64
import re

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

PUBLIC_KEY_BYTES = 65
PRIVATE_KEY_BYTES = 32
_UNCOMPRESSED_POINT_PREFIX = 0x04
# Alphabet base64url strict : un « + » ou un « / » (base64 standard) trahit
# une clé d'un autre format, refusée plutôt que convertie en silence.
_B64URL_RE = re.compile(r"[A-Za-z0-9_-]+")


def b64url_decode(value: str) -> bytes:
    """Décode du base64url (remplissage facultatif) ; `ValueError` sinon."""
    unpadded = value.rstrip("=")
    if not _B64URL_RE.fullmatch(unpadded):
        raise ValueError("base64url attendu")
    return base64.urlsafe_b64decode(unpadded + "=" * (-len(unpadded) % 4))


def b64url_encode(data: bytes) -> str:
    """Encode en base64url sans remplissage (format du Web Push)."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def load_public_key(value: str) -> ec.EllipticCurvePublicKey:
    """Point P-256 non compressé (65 octets) ; `ValueError` s'il est invalide
    (longueur, préfixe, ou point hors de la courbe)."""
    raw = b64url_decode(value)
    if len(raw) != PUBLIC_KEY_BYTES or raw[0] != _UNCOMPRESSED_POINT_PREFIX:
        raise ValueError("clé publique P-256 non compressée (65 octets) attendue")
    return ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), raw)


def load_private_key(value: str) -> ec.EllipticCurvePrivateKey:
    """Scalaire P-256 brut (32 octets) ; `ValueError` s'il est invalide."""
    raw = b64url_decode(value)
    if len(raw) != PRIVATE_KEY_BYTES:
        raise ValueError("clé privée P-256 brute (32 octets) attendue")
    # Lève ValueError pour un scalaire nul ou hors de l'ordre de la courbe.
    return ec.derive_private_key(int.from_bytes(raw, "big"), ec.SECP256R1())


def encode_public_key(key: ec.EllipticCurvePublicKey) -> str:
    raw = key.public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    return b64url_encode(raw)


def encode_private_key(key: ec.EllipticCurvePrivateKey) -> str:
    return b64url_encode(key.private_numbers().private_value.to_bytes(PRIVATE_KEY_BYTES, "big"))


def public_key_matches(public_key: str, private_key: str) -> bool:
    """Vrai si la clé publique est bien celle de la clé privée (paire
    cohérente). Les deux clés doivent être valides (sinon `ValueError`)."""
    derived = load_private_key(private_key).public_key()
    return encode_public_key(derived) == encode_public_key(load_public_key(public_key))


def generate_key_pair() -> tuple[str, str]:
    """Nouvelle paire VAPID : (clé publique, clé privée), en base64url."""
    private = ec.generate_private_key(ec.SECP256R1())
    return encode_public_key(private.public_key()), encode_private_key(private)
