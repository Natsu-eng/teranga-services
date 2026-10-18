"""Schéma de `GET /api/v1/admin/diagnostics/client-ip` (réglage des proxys)."""

from pydantic import BaseModel


class ClientIpDiagnosticOut(BaseModel):
    # Adresse de la connexion TCP vue par le backend (le dernier proxy, derrière
    # une plateforme ; le client lui-même en accès direct).
    peer: str | None
    # X-Forwarded-For tel que reçu, de gauche (le plus ancien, falsifiable) à
    # droite (ajouté par le dernier proxy).
    x_forwarded_for: list[str]
    # Réglage en vigueur (0 si absent).
    trusted_proxy_hops: int
    # Adresse retenue pour le rate limiting avec ce réglage.
    client_ip: str
