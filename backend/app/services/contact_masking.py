"""Masquage anti-fuite des coordonnées dans la messagerie (BUILD_PLAN.md §3.2,
Messagerie ; deuxième étage de la protection anti-désintermédiation après la
fiche publique sans téléphone). Aussi appliqué aux motifs de litige et
d'annulation, montrés à l'autre partie.

Appliqué À L'ENVOI, avant persistance : le texte stocké, renvoyé par l'API et
diffusé par WebSocket est toujours la version masquée. La version d'origine
n'est jamais conservée (minimisation des données) ; seul un drapeau
(`message.contact_masked`) trace la tentative, pour une future modération.

**Méthode (lot `feat/hardening-masking-otp`).** Le texte est lu sous une forme
normalisée -- chiffres de toute écriture ramenés à 0-9 (pleine largeur
« ７７ »...), emoji chiffres (« 7 + touche emoji ») réduits à leur chiffre -- puis découpé en
SUITES de chiffres (séparateurs tolérés : espaces, `. - / ( ) _ , * |`).
Dans chaque suite :

- forme internationale (`+` ou `00` en tête) : `+221` / `00221` retiré puis
  règle sénégalaise ; tout autre indicatif de 9 à 15 chiffres : la suite
  entière est masquée ;
- règle sénégalaise : CHAQUE fenêtre de 9 chiffres qui commence par
  70/75/76/77/78 (mobiles) ou 33 (fixes) est masquée, OÙ QU'ELLE SOIT dans la
  suite -- un chiffre accolé (« 77 123 45 67 8 »), deux numéros collés ou un
  zéro devant ne protègent plus le numéro.

Exceptions conservées : une suite suivie d'une devise (FCFA, CFA, F, francs,
XOF) est un montant ; une suite qui n'est qu'une date ou une heure n'est
jamais masquée. Seuls les passages masqués changent : le reste du texte est
rendu tel qu'écrit (aucune normalisation visible).

**Faux positifs ACCEPTÉS** (compromis validé, figé par les tests) : une
longue référence sans devise qui contient une fenêtre 70/75/76/77/78/33 de
9 chiffres est masquée en partie (environ 11 % des références de 10 chiffres,
26 % de 13 chiffres), de même que deux montants accolés sans devise
(« 70 000 75 000 »).

Limites assumées (documentées dans BUILD_PLAN.md) : un numéro écrit en
toutes lettres (« sept sept un... ») ou présent DANS une image n'est pas
détecté — ce serait le rôle d'une modération NLP / OCR ultérieure.
"""

import re
import unicodedata
from dataclasses import dataclass

PHONE_PLACEHOLDER = "[numéro masqué]"
EMAIL_PLACEHOLDER = "[e-mail masqué]"

# Préfixes d'un numéro sénégalais à 9 chiffres : mobiles, puis fixes.
SENEGAL_PREFIXES = frozenset({"70", "75", "76", "77", "78", "33"})
SENEGAL_NUMBER_LENGTH = 9
SENEGAL_COUNTRY_CODES = ("00221", "221")
# Numéro international explicite (« + » ou « 00 ») : 9 à 15 chiffres.
INTERNATIONAL_MIN_DIGITS = 9
INTERNATIONAL_MAX_DIGITS = 15

# Séparateurs tolérés entre deux chiffres d'une même suite.
_SEP = r"[\s.\-/()_,*|]"
# Une suite : parenthèse ouvrante et « + » / « 00 » éventuels, puis des
# chiffres séparés par des séparateurs (sur le texte NORMALISÉ).
_RUN = re.compile(rf"(?:\(\s*)?\+?\d(?:{_SEP}*\d)*")
# Devise juste après la suite : c'est un montant, jamais un numéro.
_CURRENCY_AFTER = re.compile(r"\s*(?:f\s*cfa|fcfa|cfa|xof|francs?|f)\b", re.IGNORECASE)
# Suite qui n'est qu'une date (17/10/2026, 17-10-26) ou une heure (14.30).
_DATE_OR_TIME = re.compile(r"\d{1,2}[/.\-]\d{1,2}(?:[/.\-]\d{2,4})?")
# Emoji chiffre : le chiffre, puis U+FE0F (variation) et U+20E3 (touche).
_EMOJI_DIGIT_MARKS = frozenset({chr(0xFE0F), chr(0x20E3)})

_EMAIL = re.compile(r"[\w.+\-]+@[\w\-]+(?:\.[\w\-]+)+", re.UNICODE)


@dataclass(frozen=True)
class MaskingResult:
    text: str
    # Nombre de coordonnées masquées (0 = texte inchangé).
    masked_count: int

    @property
    def masked(self) -> bool:
        return self.masked_count > 0


def _normalized_view(text: str) -> tuple[str, list[int]]:
    """Forme de LECTURE du texte : chiffres de toute écriture ramenés à 0-9,
    marques d'emoji chiffre retirées. Renvoie aussi, pour chaque caractère
    lu, sa position dans le texte d'origine (pour masquer le texte d'origine,
    jamais une version transformée)."""
    chars: list[str] = []
    origin: list[int] = []
    for index, char in enumerate(text):
        if char in _EMOJI_DIGIT_MARKS and chars and chars[-1].isdigit():
            continue
        if not char.isascii() and unicodedata.category(char) == "Nd":
            char = str(unicodedata.decimal(char))
        chars.append(char)
        origin.append(index)
    return "".join(chars), origin


def _phone_spans(view: str) -> list[tuple[int, int]]:
    """Intervalles [début, fin) à masquer, en positions de `view`."""
    spans: list[tuple[int, int]] = []
    for match in _RUN.finditer(view):
        run_start, run_end = match.span()
        run = match.group()
        if _CURRENCY_AFTER.match(view, run_end):
            continue
        if _DATE_OR_TIME.fullmatch(run.strip("( ")):
            continue
        positions = [run_start + i for i, char in enumerate(run) if char.isdigit()]
        digits = "".join(view[p] for p in positions)
        international = "+" in run[:3] or digits.startswith("00")

        offset = 0
        for code in SENEGAL_COUNTRY_CODES:
            plain_code = code.removeprefix("00")
            if digits.startswith(code) and len(digits) - len(code) >= SENEGAL_NUMBER_LENGTH:
                offset = len(code)
                break
            if (
                international
                and digits.startswith(plain_code)
                and len(digits) - len(plain_code) >= SENEGAL_NUMBER_LENGTH
            ):
                offset = len(plain_code)
                break
        if international and offset == 0:
            # Autre indicatif : un numéro étranger complet, masqué en entier.
            significant = len(digits) - (2 if digits.startswith("00") else 0)
            if INTERNATIONAL_MIN_DIGITS <= significant <= INTERNATIONAL_MAX_DIGITS:
                spans.append((run_start, positions[-1] + 1))
                continue

        k = offset
        while k + SENEGAL_NUMBER_LENGTH <= len(digits):
            if digits[k : k + 2] in SENEGAL_PREFIXES:
                end = positions[k + SENEGAL_NUMBER_LENGTH - 1] + 1
                # Fenêtre en tête de suite (ou juste après l'indicatif) : la
                # parenthèse et l'indicatif sont masqués avec le numéro.
                start = run_start if k == offset else positions[k]
                spans.append((start, end))
                k += SENEGAL_NUMBER_LENGTH
            else:
                k += 1
    return spans


def _mask_phones(text: str) -> tuple[str, int]:
    view, origin = _normalized_view(text)
    spans = _phone_spans(view)
    if not spans:
        return text, 0
    pieces: list[str] = []
    cursor = 0
    for start, end in spans:
        original_start = origin[start]
        # Fin : jusqu'au DERNIER caractère d'origine du chiffre final (un
        # emoji chiffre compte trois caractères d'origine : chiffre, U+FE0F,
        # U+20E3).
        original_end = origin[end] if end < len(origin) else len(text)
        pieces.append(text[cursor:original_start])
        pieces.append(PHONE_PLACEHOLDER)
        cursor = original_end
    pieces.append(text[cursor:])
    return "".join(pieces), len(spans)


def mask_contacts(text: str) -> MaskingResult:
    """Remplace numéros de téléphone et e-mails par une mention neutre.

    Les e-mails d'abord (un e-mail peut contenir des chiffres), puis les
    numéros. Idempotent : les mentions de remplacement ne contiennent ni
    chiffre ni « @ ».
    """
    masked, emails = _EMAIL.subn(EMAIL_PLACEHOLDER, text)
    masked, phones = _mask_phones(masked)
    return MaskingResult(text=masked, masked_count=emails + phones)
