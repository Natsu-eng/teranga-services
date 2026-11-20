"""Génère une clé secrète pour le hachage des codes OTP (OTP_HMAC_KEY).

Usage : uv run python scripts/generate_otp_hmac_key.py

Affiche la ligne à copier dans les variables d'environnement du backend
(DEPLOYMENT.md §18). Rien n'est écrit sur le disque : la clé n'existe que
dans ce terminal, puis dans le gestionnaire de secrets de l'hébergeur.

Une clé par environnement (staging, production). La changer invalide les
codes en cours (5 minutes de durée de vie) : sans effet sur les sessions.
"""

import secrets

# 32 octets aléatoires = 256 bits, encodés en base64url (43 caractères).
KEY_BYTES = 32


def main() -> None:
    print(f"OTP_HMAC_KEY={secrets.token_urlsafe(KEY_BYTES)}")
    print("# OTP_HMAC_KEY est un SECRET : jamais dans le dépôt ni dans un message.")


if __name__ == "__main__":
    main()
