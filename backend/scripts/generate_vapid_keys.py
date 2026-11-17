"""Génère une paire de clés VAPID pour les notifications push (Web Push).

Usage : uv run python scripts/generate_vapid_keys.py

Affiche les deux lignes à copier dans les variables d'environnement du
backend (DEPLOYMENT.md, « Notifications push »). Rien n'est écrit sur le
disque : la clé privée n'existe que dans ce terminal, puis dans le
gestionnaire de secrets de l'hébergeur.

Une paire par environnement (staging, production) ; ne la changer qu'en cas
de fuite : tous les appareils abonnés devraient alors se réabonner.
"""

import sys
from pathlib import Path

# `uv run python scripts/...` place le dossier scripts/ sur sys.path, pas
# backend/ : sans ceci, `import app` échoue (même recette que create_admin.py).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.vapid import generate_key_pair  # noqa: E402


def main() -> None:
    public_key, private_key = generate_key_pair()
    print(f"VAPID_PUBLIC_KEY={public_key}")
    print(f"VAPID_PRIVATE_KEY={private_key}")
    print("# VAPID_PRIVATE_KEY est un SECRET : jamais dans le dépôt ni dans un message.")


if __name__ == "__main__":
    main()
