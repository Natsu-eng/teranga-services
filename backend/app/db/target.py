"""Base de données visée par une DATABASE_URL, décrite SANS secret.

Sert aux scripts d'exploitation lancés depuis un poste (DEPLOYMENT.md §12.6) :
ils affichent la base qu'ils vont toucher avant d'agir, et le jeu de données
de démonstration refuse toute base qui n'est pas locale.
"""

from sqlalchemy.engine import make_url

from app.core.config import _LOCAL_HOSTS


def describe_database(database_url: str) -> str:
    """« hôte:port/base (utilisateur …) » -- jamais le mot de passe."""
    url = make_url(database_url)
    return f"{url.host}:{url.port or 5432}/{url.database} (utilisateur {url.username})"


def is_local_database(database_url: str) -> bool:
    """Vrai si la base est sur ce poste (localhost, 127.0.0.1, ::1...)."""
    return (make_url(database_url).host or "").lower() in _LOCAL_HOSTS
