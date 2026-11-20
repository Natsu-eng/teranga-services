"""Masquage : contournements fermés, faux positifs acceptés (lot
`feat/hardening-masking-otp`, app/services/contact_masking.py).

Les caractères invisibles sont construits avec `chr()` : aucun caractère de
contrôle ni de format écrit tel quel dans le source.
"""

import pytest

from app.services.contact_masking import PHONE_PLACEHOLDER, mask_contacts

# Emoji chiffre : le chiffre, puis U+FE0F (variation) et U+20E3 (touche).
KEYCAP = chr(0xFE0F) + chr(0x20E3)
FULLWIDTH_NUMBER = "".join(chr(0xFF10 + int(d)) for d in "771234567")
M = PHONE_PLACEHOLDER


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # Un chiffre accolé ne protège plus le numéro.
        ("77 123 45 67 8", f"{M} 8"),
        ("771234567 0", f"{M} 0"),
        ("77 123 45 678", f"{M}8"),
        ("77 123 45 67/8", f"{M}/8"),
        ("77 123 45 67.8", f"{M}.8"),
        ("Appelle 77 123 45 67 8h", f"Appelle {M} 8h"),
        ("0 77 123 45 67", f"0 {M}"),
        # Deux numéros collés : les deux sont masqués.
        ("77 123 45 67 77 123 45 68", f"{M} {M}"),
        ("771234567771234568", f"{M}{M}"),
        # Séparateurs ajoutés.
        ("77,123,45,67", M),
        ("77_123_45_67", M),
        ("77*123*45*67", M),
        ("77|123|45|67", M),
        # Écritures Unicode : chiffres pleine largeur, emoji chiffres.
        (FULLWIDTH_NUMBER, M),
        (f"7{KEYCAP}7{KEYCAP}1234567 svp", f"{M} svp"),
        # Indicatifs.
        ("+221 77 123 45 67", M),
        ("00221771234567", M),
        ("(+221) 76 123 45 67 ok", f"{M} ok"),
        ("wa.me/221781234567", f"wa.me/{M}"),
        # Un numéro juste après une date, dans la même suite.
        ("le 17/10/2026 77 123 45 67", f"le 17/10/2026 {M}"),
    ],
)
def test_masks_the_known_bypasses(text: str, expected: str) -> None:
    assert mask_contacts(text).text == expected


@pytest.mark.parametrize("prefix", ["70", "75", "76", "77", "78", "33"])
def test_every_senegalese_prefix_is_masked_wherever_it_starts(prefix: str) -> None:
    number = f"{prefix}1234567"
    for text in (number, f"9{number}", f"{number}9", f"Tél. {number} merci"):
        assert number not in mask_contacts(text).text, text


def test_only_masked_passages_change() -> None:
    full_width_five = chr(0xFF15)
    text = f"Surface 75 m², {full_width_five} pièces, appelle 7{KEYCAP}7{KEYCAP}1234567 !"
    # Le reste du texte est rendu tel qu'écrit (aucune normalisation visible).
    assert mask_contacts(text).text == f"Surface 75 m², {full_width_five} pièces, appelle {M} !"


@pytest.mark.parametrize(
    "text",
    [
        "Le devis est de 775 000 000 F",
        "Total 771 234 567 francs",
        "Payé 770000000 XOF",
        "Montant 750 000 CFA",
        "Budget total : 775 000 000 FCFA",
        "Prix : 750 000 et 330 000",
        "Rendez-vous le 12/11/2026 à 14:30.",
        "Devis n° 20261115",
        "3 300 000",
        "Entre 7h et 7h30, 75 m2",
        "Code porte 7012345",
    ],
)
def test_amounts_dates_times_and_short_numbers_are_kept(text: str) -> None:
    result = mask_contacts(text)
    assert result.text == text and not result.masked


@pytest.mark.parametrize(
    "text",
    [
        "77 123 45 67 8 ou awa@exemple.sn",
        f"Facture 7712345678901, {FULLWIDTH_NUMBER}, 0033612345678",
        "Rien à masquer ici.",
    ],
)
def test_masking_is_idempotent(text: str) -> None:
    once = mask_contacts(text).text
    assert mask_contacts(once).text == once
    assert mask_contacts(once).masked_count == 0


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # COMPROMIS VALIDÉ : une fenêtre 70/75/76/77/78/33 de 9 chiffres est
        # masquée OÙ QU'ELLE SOIT -- c'est ce qui ferme le contournement par
        # chiffre accolé. Contrepartie assumée : une longue référence sans
        # devise est masquée en partie (environ 11 % des références de 10
        # chiffres, 26 % de 13 chiffres, mesuré au diagnostic).
        ("Facture 7712345678901", f"Facture {M}8901"),
        ("Compteur n° 7712345678 (10 chiffres)", f"Compteur n° {M}8 (10 chiffres)"),
        ("IBAN SN08 7712 3456 7890", f"IBAN SN08 {M}890"),
        # Deux montants accolés SANS devise forment une seule suite.
        ("Fourchette 70 000 75 000", f"Fourchette {M}0"),
        # Un montant de 9 chiffres sans devise (avec devise : jamais masqué).
        ("Budget 775 000 000", f"Budget {M}"),
    ],
)
def test_accepted_false_positives_are_frozen(text: str, expected: str) -> None:
    assert mask_contacts(text).text == expected


def test_numbers_written_in_words_are_a_documented_limit() -> None:
    # Limite assumée (BUILD_PLAN.md) : les nombres en lettres ne sont pas traités.
    text = "sept sept un deux trois quatre cinq six sept"
    assert mask_contacts(text).text == text
