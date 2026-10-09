"""Tests unitaires du réencodage des images publiques du profil
(app/services/image_processing.py) -- sans HTTP ni base de données."""

from io import BytesIO

import pytest
from PIL import Image

from app.services.file_validation import DetectedFileType
from app.services.image_processing import (
    ImageNonDecodableError,
    ImageTropGrandeError,
    reencode_image,
)
from tests.images import (
    EXIF_GPS_IFD,
    EXIF_MAKE,
    make_jpeg,
    make_png,
    make_png_header_only,
)

_LIMITS = {"max_side_px": 1600, "max_pixels": 50_000_000}


def _open(content: bytes) -> Image.Image:
    image = Image.open(BytesIO(content))
    image.load()
    return image


def test_gps_and_device_metadata_are_stripped() -> None:
    source = make_jpeg(64, 48, with_gps=True)
    # Garde-fou : la photo d'origine porte bien la position GPS.
    assert _open(source).getexif().get_ifd(EXIF_GPS_IFD)

    result = reencode_image(source, **_LIMITS)

    exif = _open(result.content).getexif()
    assert not exif.get_ifd(EXIF_GPS_IFD)
    assert EXIF_MAKE not in exif
    assert b"TelephoneDeTest" not in result.content


def test_exif_orientation_is_applied_to_pixels() -> None:
    # Orientation 6 = « tourner de 90° » : une photo 200×100 prise en
    # portrait doit ressortir en 100×200, sans tag d'orientation résiduel.
    result = reencode_image(make_jpeg(200, 100, orientation=6), **_LIMITS)

    assert (result.width, result.height) == (100, 200)
    assert 0x0112 not in _open(result.content).getexif()


def test_large_images_are_downscaled_keeping_proportions() -> None:
    result = reencode_image(make_jpeg(3200, 1000), max_side_px=1600, max_pixels=50_000_000)

    assert (result.width, result.height) == (1600, 500)


def test_small_images_are_never_upscaled() -> None:
    result = reencode_image(make_png(100, 50), **_LIMITS)

    assert (result.width, result.height) == (100, 50)


def test_opaque_images_become_jpeg_and_transparent_ones_stay_png() -> None:
    opaque = reencode_image(make_png(40, 40), **_LIMITS)
    transparent = reencode_image(make_png(40, 40, alpha=True), **_LIMITS)

    assert opaque.detected is DetectedFileType.JPEG
    assert _open(opaque.content).format == "JPEG"
    assert transparent.detected is DetectedFileType.PNG
    assert _open(transparent.content).mode == "RGBA"


@pytest.mark.parametrize(
    "content",
    [
        b"\x89PNG\r\n\x1a\n" + b"\x00" * 64,  # signature PNG valide, contenu bidon
        make_jpeg(64, 64)[:200],  # JPEG tronqué
        b"GIF89a" + b"\x00" * 64,  # autre format
        b"",
    ],
    ids=["polyglot-png", "truncated-jpeg", "gif", "empty"],
)
def test_undecodable_content_is_rejected(content: bytes) -> None:
    with pytest.raises(ImageNonDecodableError):
        reencode_image(content, **_LIMITS)


def test_decompression_bomb_is_rejected_from_the_header_alone() -> None:
    # 64 Mpx annoncés : sous les seuils de Pillow (alerte à ~89 Mpx) mais au-delà
    # du nôtre : refusé par NOTRE contrôle, dimensions connues.
    bomb = make_png_header_only(8_000, 8_000)
    assert len(bomb) < 200

    with pytest.raises(ImageTropGrandeError) as exc_info:
        reencode_image(bomb, **_LIMITS)

    assert (exc_info.value.width, exc_info.value.height) == (8_000, 8_000)


def test_absurd_bomb_is_rejected_by_pillow_guard_as_too_large() -> None:
    # 3,6 milliards de pixels : Pillow refuse dès l'ouverture -- toujours
    # rapporté comme « trop grande », jamais comme fichier corrompu.
    with pytest.raises(ImageTropGrandeError) as exc_info:
        reencode_image(make_png_header_only(60_000, 60_000), **_LIMITS)

    assert exc_info.value.width is None


def test_output_is_much_lighter_than_a_heavy_source() -> None:
    noisy = Image.effect_noise((3000, 2000), 80).convert("RGB")
    buffer = BytesIO()
    noisy.save(buffer, format="JPEG", quality=98)
    source = buffer.getvalue()

    result = reencode_image(source, max_side_px=512, max_pixels=50_000_000)

    assert max(result.width, result.height) == 512
    assert len(result.content) < len(source) / 10
