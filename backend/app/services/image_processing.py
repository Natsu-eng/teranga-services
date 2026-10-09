"""Retraitement serveur des images PUBLIQUES du profil (avatar, couverture).

Une image envoyée n'est JAMAIS servie telle quelle : elle est entièrement
décodée puis réencodée. Ce que ça garantit, au-delà de la simple
vérification des magic bytes (`file_validation.detect_file_type`) :

- **Fichier réellement décodable** : un fichier qui commence par une
  signature PNG/JPEG valide mais n'est pas une image (polyglotte, tronqué,
  corrompu) est refusé ; ce qui est servi ne contient que des pixels
  réencodés, jamais d'octets arbitraires fournis par l'utilisateur.
- **Vie privée** : les métadonnées EXIF (position GPS de la prise de vue,
  modèle de téléphone, date...) et les blocs texte PNG sont supprimés -- ils
  seraient sinon publiés sur la fiche publique. Seul le profil colorimétrique
  ICC est conservé (rendu des couleurs, aucune donnée personnelle).
  L'orientation EXIF est appliquée aux pixels AVANT suppression, pour qu'une
  photo prise en portrait ne s'affiche pas couchée.
- **Bombe de décompression** : les dimensions sont lues dans l'en-tête et
  plafonnées (`max_pixels`) AVANT de décoder le moindre pixel -- un PNG de
  quelques Ko annonçant 50 000 × 50 000 pixels ne fait jamais allouer des
  gigaoctets. Pour un JPEG, le décodeur réduit en plus l'image dès le
  décodage (`draft`), sans jamais matérialiser la pleine résolution.
- **Taille servie maîtrisée** : redimensionnée (sans jamais agrandir) pour
  tenir dans `max_side_px` × `max_side_px`, puis recompressée -- une photo
  de téléphone de plusieurs Mo devient quelques centaines de Ko.

Fonction synchrone et coûteuse en CPU : à appeler via `asyncio.to_thread`
pour ne pas bloquer la boucle d'événements.
"""

from dataclasses import dataclass
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

from app.services.file_validation import DetectedFileType

# Qualité JPEG de sortie : 85 est le compromis usuel (artefacts invisibles à
# l'œil sur une photo, poids divisé par 3 à 5 par rapport à 95+).
JPEG_QUALITY = 85

_ACCEPTED_FORMATS = frozenset({"JPEG", "PNG"})


class ImageNonDecodableError(Exception):
    """Le contenu n'est pas une image JPEG/PNG décodable."""


class ImageTropGrandeError(Exception):
    """Dimensions annoncées au-delà du plafond de pixels. `width`/`height`
    valent `None` quand c'est le garde-fou de Pillow lui-même qui a refusé
    l'image dès son ouverture (dimensions absurdes, bien au-delà du nôtre)."""

    def __init__(self, *, width: int | None, height: int | None, max_pixels: int) -> None:
        super().__init__(f"{width}x{height} > {max_pixels} pixels")
        self.width = width
        self.height = height
        self.max_pixels = max_pixels


@dataclass(frozen=True)
class ProcessedImage:
    content: bytes
    detected: DetectedFileType
    width: int
    height: int


def _has_transparency(img: Image.Image) -> bool:
    if img.mode in ("RGBA", "LA", "PA"):
        return True
    return img.mode == "P" and "transparency" in img.info


def reencode_image(content: bytes, *, max_side_px: int, max_pixels: int) -> ProcessedImage:
    """Décode, nettoie, redimensionne et réencode `content`.

    Sortie PNG si l'image a de la transparence (logo détouré...), JPEG
    sinon (photo : bien plus léger). Lève `ImageNonDecodableError` ou
    `ImageTropGrandeError`, jamais une exception Pillow brute."""
    try:
        with Image.open(BytesIO(content)) as source:
            if source.format not in _ACCEPTED_FORMATS:
                raise ImageNonDecodableError()

            # Lu dans l'en-tête, avant tout décodage de pixels.
            width, height = source.size
            if width * height > max_pixels:
                raise ImageTropGrandeError(width=width, height=height, max_pixels=max_pixels)

            if source.format == "JPEG":
                # Décodage directement à l'échelle 1/2, 1/4 ou 1/8 la plus
                # proche au-dessus de la cible : mémoire et CPU divisés
                # d'autant, aucune perte visible après le redimensionnement.
                source.draft("RGB", (max_side_px, max_side_px))
            icc_profile = source.info.get("icc_profile")

            # Décodage COMPLET : un fichier tronqué ou corrompu échoue ici.
            source.load()
            image = ImageOps.exif_transpose(source)
    except (ImageNonDecodableError, ImageTropGrandeError):
        raise
    except Image.DecompressionBombError:
        # Seconde ligne de défense : Pillow refuse lui-même, dès l'ouverture,
        # une image au-delà de ~179 Mpx (2 × Image.MAX_IMAGE_PIXELS, laissé
        # volontairement actif).
        raise ImageTropGrandeError(width=None, height=None, max_pixels=max_pixels) from None
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError):
        raise ImageNonDecodableError() from None

    # `thumbnail` ne fait que réduire, jamais agrandir, en gardant les
    # proportions.
    image.thumbnail((max_side_px, max_side_px), Image.Resampling.LANCZOS)

    # Réencodage depuis les pixels seuls : aucune métadonnée de la source
    # n'est transmise (ni `exif=`, ni `pnginfo=`), à part l'ICC.
    output = BytesIO()
    extra = {"icc_profile": icc_profile} if icc_profile else {}
    if _has_transparency(image):
        image.convert("RGBA").save(output, format="PNG", optimize=True, **extra)
        detected = DetectedFileType.PNG
    else:
        image.convert("RGB").save(
            output, format="JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True, **extra
        )
        detected = DetectedFileType.JPEG

    return ProcessedImage(
        content=output.getvalue(), detected=detected, width=image.width, height=image.height
    )
