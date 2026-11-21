"""Schéma de `GET /api/v1/meta` : informations publiques sur l'instance."""

from pydantic import BaseModel

from app.core.config import Environment


class MetaOut(BaseModel):
    # Environnement de l'instance : le front affiche le bandeau « Version de
    # test » partout sauf en production.
    environment: Environment
    # Vrai si des numéros de test se connectent sans SMS (staging seulement).
    # Un simple booléen : la liste des numéros et le code ne sortent JAMAIS.
    otp_test_mode: bool


class NeighborhoodOut(BaseModel):
    id: str
    label: str
    # Nom de la commune dans OpenStreetMap, d'où vient le centre.
    commune: str
    department: str
    department_label: str
    # Centre officiel de la commune (OpenStreetMap) : donnée publique.
    lat: float
    lng: float


class ServiceRegionOut(BaseModel):
    # Cercle hors duquel une position GPS d'artisan est refusée.
    center_lat: float
    center_lng: float
    radius_m: int


class NeighborhoodsOut(BaseModel):
    """`GET /api/v1/meta/neighborhoods` : la liste fermée des quartiers
    desservis, seule source pour le front (aucune copie locale)."""

    items: list[NeighborhoodOut]
    # Anciens identifiants encore gardés par des téléphones -> identifiant
    # actuel (ex. « almadies » -> « ngor »).
    aliases: dict[str, str]
    # Quartier proposé tant que le client n'en a choisi aucun.
    default_id: str
    service_region: ServiceRegionOut
