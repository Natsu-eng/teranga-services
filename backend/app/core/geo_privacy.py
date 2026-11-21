"""Calculs géographiques de la vie privée des artisans (fonctions pures).

Principe : la position d'un artisan n'est JAMAIS enregistrée précise. Elle
est soit le centre officiel d'un quartier (`app.core.neighborhoods`), soit
une position GPS ramenée sur une grille régulière (`snap_to_grid`). Toute
réponse publique qui dérive de cette position (distance, couverture) ne
peut donc rien révéler de plus que ce point déjà approximatif ; la distance
affichée est en plus arrondie (`round_public_distance`).

Aucune valeur en dur ici : la taille de la grille, le pas d'arrondi et la
région desservie viennent des réglages (`app.core.config`).
"""

import math

# Rayon moyen de la Terre (IUGG), en mètres : celui que PostGIS utilise pour
# ses calculs sur une sphère. Constante physique, pas un réglage.
EARTH_RADIUS_M = 6_371_008.8
# Mètres par degré de latitude (et de longitude à l'équateur).
METERS_PER_DEGREE = EARTH_RADIUS_M * math.pi / 180
# Précision d'enregistrement des coordonnées : 6 décimales (~0,1 m), bien
# en deçà de toute grille utile -- évite seulement les queues flottantes.
_COORDINATE_DECIMALS = 6


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Distance sur la sphère entre deux points, en mètres."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = phi2 - phi1
    d_lambda = math.radians(lng2 - lng1)
    h = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(h))


def snap_to_grid(
    lat: float, lng: float, *, grid_m: int, reference_lat: float
) -> tuple[float, float]:
    """Ramène un point sur le nœud le plus proche d'une grille de `grid_m`
    mètres de côté.

    La grille est FIXE : son pas en longitude est calculé à la latitude de
    référence (le centre de la région desservie), jamais à celle du point.
    Deux positions de la même maille donnent donc exactement le même nœud,
    et aucune réponse ne permet de les distinguer. Écart maximal entre la
    position réelle et le point enregistré : la demi-diagonale d'une maille
    (~354 m pour 500 m).
    """
    lat_step = grid_m / METERS_PER_DEGREE
    lng_step = grid_m / (METERS_PER_DEGREE * math.cos(math.radians(reference_lat)))
    snapped_lat = round(round(lat / lat_step) * lat_step, _COORDINATE_DECIMALS)
    snapped_lng = round(round(lng / lng_step) * lng_step, _COORDINATE_DECIMALS)
    return snapped_lat, snapped_lng


def round_public_distance(distance_m: float, *, step_m: int) -> int:
    """Distance publique : arrondie au multiple SUPÉRIEUR de `step_m`, jamais
    moins d'un pas (« à moins de 500 m » plutôt que « 0 m », qui suggérerait
    une adresse). Le multiple supérieur ne sous-estime jamais la distance."""
    if distance_m <= 0:
        return step_m
    return max(step_m, math.ceil(distance_m / step_m) * step_m)
