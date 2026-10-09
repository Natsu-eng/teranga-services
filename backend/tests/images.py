"""Images de test réelles (décodables par Pillow), générées à la volée --
aucun fichier binaire versionné. Utilisées partout où un upload de photo de
profil/couverture est testé : depuis le réencodage serveur
(app/services/image_processing.py), une simple signature PNG suivie
d'octets nuls n'est plus acceptée -- à juste titre.
"""

import struct
import zlib
from io import BytesIO

from PIL import Image

# Tags EXIF utilisés par les tests de nettoyage des métadonnées.
EXIF_ORIENTATION = 0x0112
EXIF_GPS_IFD = 0x8825
EXIF_MAKE = 0x010F


def make_png(
    width: int = 32, height: int = 32, color: tuple[int, ...] = (14, 90, 60), *, alpha: bool = False
) -> bytes:
    mode = "RGBA" if alpha else "RGB"
    fill = color if not alpha or len(color) == 4 else (*color, 128)
    buffer = BytesIO()
    Image.new(mode, (width, height), fill).save(buffer, format="PNG")
    return buffer.getvalue()


def make_jpeg(
    width: int = 32,
    height: int = 32,
    color: tuple[int, int, int] = (200, 120, 40),
    *,
    with_gps: bool = False,
    orientation: int | None = None,
) -> bytes:
    """JPEG, avec en option une position GPS (Dakar) et un fabricant
    d'appareil dans l'EXIF, et/ou un tag d'orientation."""
    image = Image.new("RGB", (width, height), color)
    exif = Image.Exif()
    if with_gps:
        exif[EXIF_MAKE] = "TelephoneDeTest"
        # GPSLatitudeRef/GPSLatitude/GPSLongitudeRef/GPSLongitude.
        exif.get_ifd(EXIF_GPS_IFD).update(
            {1: "N", 2: (14.0, 41.0, 0.0), 3: "W", 4: (17.0, 26.0, 0.0)}
        )
    if orientation is not None:
        exif[EXIF_ORIENTATION] = orientation
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=90, exif=exif.tobytes() if len(exif) else b"")
    return buffer.getvalue()


def make_png_header_only(width: int, height: int) -> bytes:
    """PNG minuscule dont l'en-tête annonce `width` × `height` pixels --
    modèle de bombe de décompression, sans jamais allouer ces pixels côté
    test."""

    def chunk(kind: bytes, payload: bytes) -> bytes:
        body = kind + payload
        return struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body))

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(b"\x00" * 64))
        + chunk(b"IEND", b"")
    )
