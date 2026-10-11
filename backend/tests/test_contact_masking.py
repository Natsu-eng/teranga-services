"""Preuve du masquage anti-fuite (app.services.contact_masking).

Deux exigences d'égale importance : masquer TOUS les formats courants d'un
numéro (et un e-mail), et ne JAMAIS dégrader un message normal qui contient
des chiffres (quantités, dimensions, montants, dates, heures).
"""

import pytest

from app.services.contact_masking import EMAIL_PLACEHOLDER, PHONE_PLACEHOLDER, mask_contacts


@pytest.mark.parametrize(
    "number",
    [
        "771234567",
        "77 123 45 67",
        "77.123.45.67",
        "77-123-45-67",
        "77/123/45/67",
        "+221771234567",
        "+221 77 123 45 67",
        "+221-77-123-45-67",
        "00221771234567",
        "00221 77 123 45 67",
        "221771234567",
        "(+221) 77 123 45 67",
        "7 7 1 2 3 4 5 6 7",
        "70 123 45 67",
        "75 123 45 67",
        "76 123 45 67",
        "78 123 45 67",
        "33 821 23 45",
    ],
)
def test_masks_every_senegalese_number_format(number: str) -> None:
    result = mask_contacts(f"Appelle-moi au {number} ce soir.")

    assert result.text == f"Appelle-moi au {PHONE_PLACEHOLDER} ce soir."
    assert result.masked
    assert result.masked_count == 1


@pytest.mark.parametrize(
    "text",
    [
        "Mon WhatsApp : wa.me/221771234567",
        "Numéro en France : +33 6 12 34 56 78",
        "Ou bien 0033612345678",
    ],
)
def test_masks_messaging_links_and_international_numbers(text: str) -> None:
    result = mask_contacts(text)

    assert PHONE_PLACEHOLDER in result.text
    assert not any(char.isdigit() for char in result.text.split(":")[-1].replace("wa.me/", ""))


def test_masks_email_addresses() -> None:
    result = mask_contacts("Écris-moi sur awa.diop+chantier@gmail.com stp")

    assert result.text == f"Écris-moi sur {EMAIL_PLACEHOLDER} stp"
    assert result.masked_count == 1


def test_masks_several_contacts_in_one_message() -> None:
    result = mask_contacts("77 123 45 67 ou 76 765 43 21, sinon awa@exemple.sn")

    assert result.text == f"{PHONE_PLACEHOLDER} ou {PHONE_PLACEHOLDER}, sinon {EMAIL_PLACEHOLDER}"
    assert result.masked_count == 3


@pytest.mark.parametrize(
    "text",
    [
        "Il faut 2 robinets de 15 mm.",
        "Prévoir 3 tuyaux de 1,5 m et 12 coudes.",
        "Le devis est de 75 000 FCFA.",
        "Budget total : 775 000 000 FCFA",
        "Entre 70 000 et 75 000 F selon le matériel.",
        "Fourchette 70 000 75 000",
        "Rendez-vous le 17/10/2026 à 14h30.",
        "Je suis disponible de 8h à 18h, appartement 7, 3e étage.",
        "Surface : 150 m², hauteur 2,70 m.",
        "Référence commande 2077123456",
        "Compteur n° 7712345678 (10 chiffres)",
        "Promo -15 % sur 77 articles",
        "Ticket @Idrissa merci",
    ],
)
def test_never_over_masks_ordinary_text_with_numbers(text: str) -> None:
    result = mask_contacts(text)

    assert result.text == text
    assert not result.masked
    assert result.masked_count == 0
