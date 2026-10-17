"""Génère les icônes PNG de l'application installable (PWA) à partir du
monogramme du favicon (public/favicon.svg) : « T » or (#e8a73b) sur vert
profond (#004129), les couleurs de la charte (DESIGN_SYSTEM.md).

Usage (depuis la racine du dépôt ; Pillow fourni à la volée par uv, aucune
dépendance ajoutée au projet) :

    uv run --no-project --with pillow python frontend/scripts/generate_pwa_icons.py

Icônes produites dans frontend/public/icons/ :
- icon-192.png, icon-512.png : usage « any » (Android, écran d'accueil) ;
- icon-maskable-512.png : usage « maskable » — Android peut rogner l'icône
  en cercle ou en goutte : le « T » tient dans la zone sûre (cercle de 80 %
  du côté, centré), le fond couvre tout le carré ;
- apple-touch-icon.png (180 px) : écran d'accueil iPhone (iOS arrondit les
  angles lui-même : carré plein, sans transparence).

Le dessin reprend EXACTEMENT le tracé du favicon (grille 64 × 64) ;
suréchantillonnage x4 puis réduction : bords nets à toutes les tailles.
"""

from pathlib import Path

from PIL import Image, ImageDraw

GREEN = (0x00, 0x41, 0x29, 255)
GOLD = (0xE8, 0xA7, 0x3B, 255)
# Tracé du « T » du favicon : M18 18h28v8H36v22h-8V26H18z (grille 64).
T_PATH = [(18, 18), (46, 18), (46, 26), (36, 26), (36, 48), (28, 48), (28, 26), (18, 26)]
OUT = Path(__file__).resolve().parents[1] / "public" / "icons"


def render(size: int, *, glyph_scale: float) -> Image.Image:
    """Carré plein vert, « T » centré ; `glyph_scale` réduit le « T » autour
    du centre (1.0 = proportions exactes du favicon)."""
    big = size * 4
    image = Image.new("RGBA", (big, big), GREEN)
    unit = big / 64
    center = 32
    points = [
        (
            (center + (x - center) * glyph_scale) * unit,
            (center + (y - center) * glyph_scale) * unit,
        )
        for x, y in T_PATH
    ]
    ImageDraw.Draw(image).polygon(points, fill=GOLD)
    return image.resize((size, size), Image.Resampling.LANCZOS)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    # Point du « T » le plus éloigné du centre (32, 32) : les coins (18, 18) et
    # (46, 18), à √(14² + 14²) ≈ 19,8 unités. Zone sûre maskable = cercle de
    # rayon 0,4 × 64 = 25,6 : le tracé d'origine y tient déjà ; 0,9 ajoute
    # une marge (≈ 17,8) pour les masques les plus serrés.
    targets = {
        "icon-192.png": (192, 1.0),
        "icon-512.png": (512, 1.0),
        "icon-maskable-512.png": (512, 0.9),
        "apple-touch-icon.png": (180, 1.0),
    }
    for name, (size, scale) in targets.items():
        image = render(size, glyph_scale=scale)
        if name == "apple-touch-icon.png":
            image = image.convert("RGB")  # iOS : aucune transparence
        image.save(OUT / name, optimize=True)
        print(f"{name} : {size}x{size}")


if __name__ == "__main__":
    main()
