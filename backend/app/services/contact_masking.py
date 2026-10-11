"""Masquage anti-fuite des coordonnées dans la messagerie (BUILD_PLAN.md §3.2,
Messagerie ; deuxième étage de la protection anti-désintermédiation après la
fiche publique sans téléphone).

Appliqué À L'ENVOI, avant persistance : le texte stocké, renvoyé par l'API et
diffusé par WebSocket est toujours la version masquée. La version d'origine
n'est jamais conservée (minimisation des données) ; seul un drapeau
(`message.contact_masked`) trace la tentative, pour une future modération.

Ce qui est masqué :
- numéros sénégalais à 9 chiffres : mobiles 70/75/76/77/78 et fixes 33,
  suivis de 7 chiffres, avec ou sans indicatif (+221, 00221, 221), quels que
  soient les séparateurs (espaces, points, tirets, barres, parenthèses) — y
  compris l'espacement chiffre par chiffre (« 7 7 1 2 3 … »), parade
  classique de contournement ;
- numéros internationaux explicites (« + » ou « 00 » suivi de 9 à 15
  chiffres), pour ne pas laisser passer un numéro étranger ;
- adresses e-mail.

Ce qui n'est PAS masqué (garde-fous contre le sur-masquage, prouvés par les
tests) : nombres plus longs ou collés à d'autres chiffres, montants suivis
d'une devise (« 775 000 000 FCFA »), dimensions, quantités, dates, heures.

Limites assumées (documentées dans BUILD_PLAN.md) : un numéro écrit en
toutes lettres (« sept sept un... ») ou présent DANS une image n'est pas
détecté — ce serait le rôle d'une modération NLP / OCR ultérieure.
"""

import re
from dataclasses import dataclass

PHONE_PLACEHOLDER = "[numéro masqué]"
EMAIL_PLACEHOLDER = "[e-mail masqué]"

# Séparateurs tolérés entre deux chiffres d'un même numéro.
_SEP = r"[\s.\-/()]*"

_SENEGAL_PHONE = re.compile(
    rf"""
    (?<![\d+])                      # pas collé à un chiffre ou à un « + » qui précède
    (?:\(\s*)?                     # parenthèse ouvrante éventuelle : « (+221) ... »
    (?:
        (?:\+|00){_SEP}2{_SEP}2{_SEP}1{_SEP}   # indicatif +221 / 00221
      | 2{_SEP}2{_SEP}1{_SEP}                  # indicatif sans « + » (ex. wa.me/221...)
    )?
    (?:7{_SEP}[05678]|3{_SEP}3)     # mobiles 70/75/76/77/78, fixes 33
    (?:{_SEP}\d){{7}}               # puis exactement 7 chiffres
    (?!{_SEP}\d)                    # jamais le début d'un nombre plus long
    (?!{_SEP}(?:f\s*cfa|fcfa|cfa|xof|francs?|f)\b)   # ni un montant
    """,
    re.VERBOSE | re.IGNORECASE,
)

_INTERNATIONAL_PHONE = re.compile(
    rf"""
    (?<![\w+])                      # pas collé à un mot ou à un autre « + »
    (?:\+|00){_SEP}[1-9]            # « + » ou « 00 », puis indicatif pays
    (?:{_SEP}\d){{8,14}}            # 9 à 15 chiffres au total
    (?!{_SEP}\d)
    """,
    re.VERBOSE,
)

_EMAIL = re.compile(r"[\w.+\-]+@[\w\-]+(?:\.[\w\-]+)+", re.UNICODE)


@dataclass(frozen=True)
class MaskingResult:
    text: str
    # Nombre de coordonnées masquées (0 = texte inchangé).
    masked_count: int

    @property
    def masked(self) -> bool:
        return self.masked_count > 0


def mask_contacts(text: str) -> MaskingResult:
    """Remplace numéros de téléphone et e-mails par une mention neutre.

    L'ordre compte : les e-mails d'abord (un e-mail peut contenir des
    chiffres), puis les numéros sénégalais (règle la plus précise), puis les
    numéros internationaux restants.
    """
    count = 0
    masked = text
    for pattern, placeholder in (
        (_EMAIL, EMAIL_PLACEHOLDER),
        (_SENEGAL_PHONE, PHONE_PLACEHOLDER),
        (_INTERNATIONAL_PHONE, PHONE_PLACEHOLDER),
    ):
        masked, replaced = pattern.subn(placeholder, masked)
        count += replaced
    return MaskingResult(text=masked, masked_count=count)
