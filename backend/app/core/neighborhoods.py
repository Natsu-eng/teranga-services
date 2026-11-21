"""Quartiers desservis : liste FERMÉE, source unique côté serveur.

Une entrée par COMMUNE de la région de Dakar (ses 5 départements : Dakar,
Pikine, Guédiawaye, Keur Massar, Rufisque), sans sous-quartier. Le front ne
garde aucune copie : il lit `GET /api/v1/meta/neighborhoods`.

Provenance des coordonnées : OpenStreetMap, jamais saisies à la main.
- Chaque commune est la relation OSM `boundary=administrative`,
  `admin_level=8`, dont l'identifiant figure dans `osm_relation`.
- Le centre est le point que Nominatim attribue à cette relation (son nœud
  `label`/`admin_centre`, sinon son centroïde), arrondi à 5 décimales
  (~1 m). Vérifié : chaque centre tombe DANS le polygone de sa commune.
- Le département est établi par inclusion du centre dans les polygones OSM
  des 5 départements (aucune commune ambiguë) : 19 + 12 + 5 + 6 + 11 = 53.
- Relevé du 2026-11-21. Données © les contributeurs d'OpenStreetMap,
  licence ODbL.

Identifiants : stables, car gardés sur les téléphones des clients (quartier
choisi). Les 6 historiques sont CONSERVÉS : `plateau`, `ouakam`,
`mermoz-sacre-coeur`, `point-e` (commune Fann-Point E-Amitié) sont des
communes ; `almadies` et `yoff-ngor` n'en sont pas et deviennent des alias
(`LEGACY_ALIASES`) vers la commune où tombait leur ancien point.
"""

from dataclasses import dataclass
from enum import StrEnum


class Department(StrEnum):
    DAKAR = "dakar"
    PIKINE = "pikine"
    GUEDIAWAYE = "guediawaye"
    KEUR_MASSAR = "keur_massar"
    RUFISQUE = "rufisque"


DEPARTMENT_LABELS: dict[Department, str] = {
    Department.DAKAR: "Dakar",
    Department.PIKINE: "Pikine",
    Department.GUEDIAWAYE: "Guédiawaye",
    Department.KEUR_MASSAR: "Keur Massar",
    Department.RUFISQUE: "Rufisque",
}


@dataclass(frozen=True, slots=True)
class Neighborhood:
    # Identifiant stable (gardé par les téléphones et en base).
    id: str
    # Libellé affiché.
    label: str
    # Nom de la commune tel qu'il figure dans OpenStreetMap.
    osm_name: str
    department: Department
    # Centre de la commune (OSM), en degrés WGS 84.
    lat: float
    lng: float
    # Relation OSM d'où viennent le nom, le centre et le département.
    osm_relation: int


NEIGHBORHOODS: tuple[Neighborhood, ...] = (
    # --- Département de Dakar (19 communes) ---
    Neighborhood(
        "plateau",
        "Dakar-Plateau",
        "Commune de Dakar-Plateau",
        Department.DAKAR,
        14.66732,
        -17.43797,
        12989256,
    ),
    Neighborhood(
        "biscuiterie",
        "Biscuiterie",
        "Commune de Biscuiterie",
        Department.DAKAR,
        14.70945,
        -17.44983,
        4596980,
    ),
    Neighborhood(
        "camberene",
        "Cambérène",
        "Commune de Cambérène",
        Department.DAKAR,
        14.771,
        -17.4237,
        12982370,
    ),
    Neighborhood(
        "dieuppeul-derkle",
        "Dieuppeul-Derklé",
        "Commune de Dieuppeul-Derklé",
        Department.DAKAR,
        14.71981,
        -17.45323,
        12988837,
    ),
    Neighborhood(
        "point-e",
        "Fann-Point E-Amitié",
        "Commune de Fann-Point E-Amitié",
        Department.DAKAR,
        14.69403,
        -17.46213,
        12989253,
    ),
    Neighborhood(
        "goree", "Gorée", "Commune de Gorée", Department.DAKAR, 14.66641, -17.39828, 12989257
    ),
    Neighborhood(
        "grand-dakar",
        "Grand Dakar",
        "Commune de Grand-Dakar",
        Department.DAKAR,
        14.70546,
        -17.45411,
        6998697,
    ),
    Neighborhood(
        "grand-yoff",
        "Grand Yoff",
        "Commune de Grand Yoff",
        Department.DAKAR,
        14.73668,
        -17.45281,
        12982373,
    ),
    Neighborhood(
        "gueule-tapee-fass-colobane",
        "Gueule Tapée-Fass-Colobane",
        "Commune de Gueule Tapée-Fass-Colobane",
        Department.DAKAR,
        14.68828,
        -17.45537,
        12989254,
    ),
    Neighborhood("hlm", "HLM", "Commune de HLM", Department.DAKAR, 14.71007, -17.44418, 12988836),
    Neighborhood(
        "hann-bel-air",
        "Hann Bel-Air",
        "Commune de Hann Bel-Air",
        Department.DAKAR,
        14.71564,
        -17.43556,
        12988835,
    ),
    Neighborhood(
        "sicap-liberte",
        "Sicap-Liberté",
        "Commune de Sicap-Liberté",
        Department.DAKAR,
        14.723,
        -17.46159,
        12988838,
    ),
    Neighborhood(
        "medina", "Médina", "Commune de Médina", Department.DAKAR, 14.68049, -17.45093, 12989255
    ),
    Neighborhood(
        "mermoz-sacre-coeur",
        "Mermoz-Sacré-Cœur",
        "Commune de Mermoz-Sacré-Cœur",
        Department.DAKAR,
        14.70573,
        -17.46921,
        12988611,
    ),
    Neighborhood(
        "ngor", "Ngor", "Commune de Ngor", Department.DAKAR, 14.74879, -17.51496, 12988609
    ),
    Neighborhood(
        "ouakam", "Ouakam", "Commune de Ouakam", Department.DAKAR, 14.72474, -17.48507, 12988610
    ),
    Neighborhood(
        "parcelles-assainies",
        "Parcelles Assainies",
        "Commune de Parcelles Assainies",
        Department.DAKAR,
        14.75941,
        -17.43845,
        12982372,
    ),
    Neighborhood(
        "patte-d-oie",
        "Patte d'Oie",
        "Commune de Patte d'Oie",
        Department.DAKAR,
        14.74649,
        -17.44069,
        12982371,
    ),
    Neighborhood(
        "yoff", "Yoff", "Commune de Yoff", Department.DAKAR, 14.76036, -17.46815, 12988608
    ),
    # --- Département de Pikine (12 communes) ---
    Neighborhood(
        "dalifort",
        "Dalifort",
        "Commune de Dalifort",
        Department.PIKINE,
        14.74149,
        -17.40931,
        12989302,
    ),
    Neighborhood(
        "djiddah-thiaroye-kao",
        "Djiddah Thiaroye Kao",
        "Commune de Djidah Thiaroye Kaw",
        Department.PIKINE,
        14.76527,
        -17.383,
        12989308,
    ),
    Neighborhood(
        "guinaw-rail-nord",
        "Guinaw Rail Nord",
        "Commune de Guinaw Rail Nord",
        Department.PIKINE,
        14.75367,
        -17.38359,
        12989306,
    ),
    Neighborhood(
        "guinaw-rail-sud",
        "Guinaw Rail Sud",
        "Commune de Guinaw Rail Sud",
        Department.PIKINE,
        14.74816,
        -17.38364,
        12989305,
    ),
    Neighborhood(
        "pikine-est",
        "Pikine Est",
        "Commune de Pikine Est",
        Department.PIKINE,
        14.75728,
        -17.38759,
        12989307,
    ),
    Neighborhood(
        "pikine-nord",
        "Pikine Nord",
        "Commune de Pikine Nord",
        Department.PIKINE,
        14.76046,
        -17.39553,
        12989304,
    ),
    Neighborhood(
        "pikine-ouest",
        "Pikine Ouest",
        "Commune de Pikine Ouest",
        Department.PIKINE,
        14.75466,
        -17.39869,
        12989303,
    ),
    Neighborhood(
        "mbao", "Mbao", "Commune de Mbao", Department.PIKINE, 14.74154, -17.32615, 12989393
    ),
    Neighborhood(
        "diamaguene-sicap-mbao",
        "Diamaguène Sicap Mbao",
        "Commune de Diamaguène-Sicap Mbao",
        Department.PIKINE,
        14.75606,
        -17.35159,
        12989397,
    ),
    Neighborhood(
        "thiaroye-gare",
        "Thiaroye Gare",
        "Commune de Thiaroye-Gare",
        Department.PIKINE,
        14.75727,
        -17.37404,
        12989396,
    ),
    Neighborhood(
        "thiaroye-sur-mer",
        "Thiaroye-sur-Mer",
        "Commune de Thiaroye-sur-Mer",
        Department.PIKINE,
        14.74122,
        -17.37497,
        12989394,
    ),
    Neighborhood(
        "tivaouane-diacksao",
        "Tivaouane Diacksao",
        "Commune de Tivaouane Diacksao",
        Department.PIKINE,
        14.75023,
        -17.36946,
        12989395,
    ),
    # --- Département de Guédiawaye (5 communes) ---
    Neighborhood(
        "golf-sud",
        "Golf Sud",
        "Commune du Golf Sud",
        Department.GUEDIAWAYE,
        14.7717,
        -17.40891,
        12982144,
    ),
    Neighborhood(
        "medina-gounass",
        "Médina Gounass",
        "Commune de Medina Gounass",
        Department.GUEDIAWAYE,
        14.7717,
        -17.38204,
        12982140,
    ),
    Neighborhood(
        "ndiareme-limamoulaye",
        "Ndiarème Limamoulaye",
        "Commune de Ndiarème Limamoulaye",
        Department.GUEDIAWAYE,
        14.79529,
        -17.39225,
        12982143,
    ),
    Neighborhood(
        "sam-notaire",
        "Sam Notaire",
        "Commune de Sam Notaire",
        Department.GUEDIAWAYE,
        14.78403,
        -17.39742,
        12982142,
    ),
    Neighborhood(
        "wakhinane-nimzatt",
        "Wakhinane Nimzatt",
        "Commune de Wakhinane Nimzatt",
        Department.GUEDIAWAYE,
        14.79684,
        -17.37466,
        12982141,
    ),
    # --- Département de Keur Massar (6 communes) ---
    Neighborhood(
        "keur-massar-nord",
        "Keur Massar Nord",
        "Commune de Keur Massar Nord",
        Department.KEUR_MASSAR,
        14.78772,
        -17.31224,
        12982149,
    ),
    Neighborhood(
        "keur-massar-sud",
        "Keur Massar Sud",
        "Commune de Keur Massar Sud",
        Department.KEUR_MASSAR,
        14.77005,
        -17.3083,
        13067451,
    ),
    Neighborhood(
        "malika",
        "Malika",
        "Commune de Malika",
        Department.KEUR_MASSAR,
        14.80148,
        -17.3376,
        12982148,
    ),
    Neighborhood(
        "yeumbeul-nord",
        "Yeumbeul Nord",
        "Commune de Yeumbeul Nord",
        Department.KEUR_MASSAR,
        14.79225,
        -17.35495,
        12982147,
    ),
    Neighborhood(
        "yeumbeul-sud",
        "Yeumbeul Sud",
        "Commune de Yeumbeul Sud",
        Department.KEUR_MASSAR,
        14.76997,
        -17.36412,
        12982150,
    ),
    Neighborhood(
        "jaxaay-parcelles",
        "Jaxaay-Parcelles",
        "Commune de Jaxaay - Parcelles",
        Department.KEUR_MASSAR,
        14.77057,
        -17.28237,
        12982160,
    ),
    # --- Département de Rufisque (11 communes) ---
    Neighborhood(
        "rufisque-est",
        "Rufisque Est",
        "Commune de Rufisque Est",
        Department.RUFISQUE,
        14.71765,
        -17.2551,
        12982167,
    ),
    Neighborhood(
        "rufisque-nord",
        "Rufisque Nord",
        "Commune de Rufisque Nord",
        Department.RUFISQUE,
        14.72971,
        -17.27132,
        12982158,
    ),
    Neighborhood(
        "rufisque-ouest",
        "Rufisque Ouest",
        "Commune de Rufisque Ouest",
        Department.RUFISQUE,
        14.74375,
        -17.29793,
        12982157,
    ),
    Neighborhood(
        "bargny", "Bargny", "Commune de Bargny", Department.RUFISQUE, 14.69383, -17.22974, 12982162
    ),
    Neighborhood(
        "sebikotane",
        "Sébikotane",
        "Commune de Sébikhotane",
        Department.RUFISQUE,
        14.74075,
        -17.13908,
        12982163,
    ),
    Neighborhood(
        "diamniadio",
        "Diamniadio",
        "Commune de Diamniadio",
        Department.RUFISQUE,
        14.72022,
        -17.18424,
        12982164,
    ),
    Neighborhood(
        "sendou", "Sendou", "Commune de Sendou", Department.RUFISQUE, 14.67072, -17.20459, 12982161
    ),
    Neighborhood(
        "bambilor",
        "Bambilor",
        "Commune de Bambylor",
        Department.RUFISQUE,
        14.83422,
        -17.18425,
        12982154,
    ),
    Neighborhood(
        "sangalkam",
        "Sangalkam",
        "Commune de Sangalkam",
        Department.RUFISQUE,
        14.7793,
        -17.22826,
        12982168,
    ),
    Neighborhood(
        "yene",
        "Yène",
        "Communauté rurale de Yenne",
        Department.RUFISQUE,
        14.64522,
        -17.16337,
        12982155,
    ),
    Neighborhood(
        "tivaouane-peulh-niaga",
        "Tivaouane Peulh-Niaga",
        "Commune de Tivaouane Peulh-Niaga",
        Department.RUFISQUE,
        14.83022,
        -17.26595,
        12982153,
    ),
)

# Anciens identifiants qui ne sont pas des communes -> commune où tombait
# leur ancien point (vérifié dans les polygones OSM) : l'ancien point
# « Almadies » (et la relation OSM « Arrondissement des Almadies ») est dans
# la commune de Ngor ; l'ancien point « Yoff / Ngor » dans celle de Yoff.
LEGACY_ALIASES: dict[str, str] = {
    "almadies": "ngor",
    "yoff-ngor": "yoff",
}

_BY_ID: dict[str, Neighborhood] = {n.id: n for n in NEIGHBORHOODS}

# Quartier proposé par défaut au client qui n'en a encore choisi aucun
# (inchangé : c'était déjà le Plateau).
DEFAULT_NEIGHBORHOOD_ID = "plateau"


def resolve_neighborhood(neighborhood_id: str) -> Neighborhood | None:
    """Le quartier de cet identifiant (alias historiques compris), ou `None`
    s'il n'appartient pas à la liste fermée."""
    canonical = LEGACY_ALIASES.get(neighborhood_id, neighborhood_id)
    return _BY_ID.get(canonical)
