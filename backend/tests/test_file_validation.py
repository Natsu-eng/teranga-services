"""Détection du type réel d'un fichier par magic bytes (BUILD_PLAN.md,
onboarding artisan) -- jamais par extension ni Content-Type déclaré."""

from app.services.file_validation import DetectedFileType, detect_file_type

_JPEG_HEADER = b"\xff\xd8\xff\xe0\x00\x10JFIF"
_PNG_HEADER = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
_PDF_HEADER = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3"


def test_detects_jpeg_from_header() -> None:
    assert detect_file_type(_JPEG_HEADER) is DetectedFileType.JPEG


def test_detects_png_from_header() -> None:
    assert detect_file_type(_PNG_HEADER) is DetectedFileType.PNG


def test_detects_pdf_from_header() -> None:
    assert detect_file_type(_PDF_HEADER) is DetectedFileType.PDF


def test_rejects_plain_text_renamed_as_image() -> None:
    """Un fichier texte, quel que soit son nom/extension déclarée, n'a
    aucune signature reconnue -- c'est exactement le scénario "extension
    falsifiée" que l'upload doit rejeter."""
    fake = b"ceci n'est pas une image, juste du texte brut renomme en .jpg"
    assert detect_file_type(fake) is None


def test_rejects_executable_disguised_as_pdf() -> None:
    windows_exe_header = b"MZ\x90\x00\x03\x00\x00\x00"
    assert detect_file_type(windows_exe_header) is None


def test_rejects_empty_content() -> None:
    assert detect_file_type(b"") is None
