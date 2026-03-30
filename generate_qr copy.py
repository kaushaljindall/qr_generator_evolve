"""
generate_qr.py
--------------
Production-ready QR code generation module using `segno` + `Pillow`.

Usage (CLI):
    python generate_qr.py

Usage (as a library):
    from generate_qr import generate_qr

    # Standard QR
    path = generate_qr("https://example.com", evolve=False)

    # Styled branded QR with logo
    path = generate_qr("https://example.com", evolve=True, logo_path="assets/logo/logo.png")

    # Return as BytesIO for API use
    buf = generate_qr("https://example.com", evolve=True, return_bytes=True)
"""

import io
import os
import math
from datetime import datetime
from urllib.parse import urlparse

import segno
from PIL import Image, ImageDraw


# ─────────────────────────────────────────────
# STYLE CONFIG  (change here to restyle globally)
# ─────────────────────────────────────────────
STYLE_CONFIG = {
    # QR module colors
    "dark_color":       "#E63946",   # primary red  – data modules
    "light_color":      "#FFFFFF",   # white background
    "finder_dark":      "#E63946",   # finder pattern outer squares
    "finder_light":     "#FFFFFF",   # finder pattern inner fill
    # Logo sizing
    "logo_ratio":       0.22,        # logo = 22 % of QR side
    # Output
    "scale":            12,          # pixels per module (higher = larger image)
    "border":           4,           # quiet zone modules
}


# ─────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────

def generate_qr(
    data: str,
    evolve: bool = False,
    logo_path: str | None = None,
    output_dir: str = "output_qr",
    transparent: bool = False,
    output_format: str = "png",   # "png" | "svg"
    return_bytes: bool = False,
) -> io.BytesIO | str:
    """
    Main entry point.

    Args:
        data         : URL or any string to encode.
        evolve       : False → standard black QR. True → branded styled QR.
        logo_path    : Optional path to logo image (PNG recommended, RGBA).
        output_dir   : Directory to save the file (ignored when return_bytes=True).
        transparent  : Use transparent background instead of white.
        output_format: "png" or "svg".
        return_bytes : If True, returns a BytesIO object instead of saving to disk.

    Returns:
        str      – absolute path to saved file  (when return_bytes=False)
        BytesIO  – in-memory image buffer       (when return_bytes=True)
    """
    data = _normalise_url(data)

    # ── Generate raw QR via segno ──────────────────────────────────
    qr = segno.make(data, error="H", boost_error=False)

    if output_format == "svg":
        return _export_svg(qr, data, output_dir, return_bytes)

    # ── Build PNG image ────────────────────────────────────────────
    if evolve:
        img = apply_evolve_style(qr, transparent=transparent)
    else:
        img = _render_standard(qr, transparent=transparent)

    # ── Embed logo (optional) ──────────────────────────────────────
    if logo_path:
        img = embed_logo(img, logo_path)

    # ── Output ─────────────────────────────────────────────────────
    if return_bytes:
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return buf

    return _save(img, data, output_dir, prefix="Evolve_" if evolve else "")


# ─────────────────────────────────────────────
# CORE RENDER FUNCTIONS
# ─────────────────────────────────────────────

def _render_standard(qr, transparent: bool = False) -> Image.Image:
    """Render a clean black-on-white (or transparent) QR code."""
    scale  = STYLE_CONFIG["scale"]
    border = STYLE_CONFIG["border"]

    buf = io.BytesIO()
    back = None if transparent else "#FFFFFF"   # segno: None = transparent
    qr.save(buf, kind="png", scale=scale, border=border,
            dark="#000000", light=back)
    buf.seek(0)
    return Image.open(buf).convert("RGBA")


def apply_evolve_style(qr, transparent: bool = False) -> Image.Image:
    """
    Render a fully styled, branded QR code.

    Strategy
    --------
    segno's save() accepts `dark` and `light` for module colors, but finder
    patterns share the same dark color. To give finders a distinct color we
    do a two-pass pixel replacement on the rendered image:

    Pass 1 – render with primary red for all dark modules.
    Pass 2 – locate finder-pattern regions and repaint them with accent blue.

    This keeps the QR fully scannable (contrast is maintained) while giving
    the visual look of the example image (red data + blue finder accents).
    """
    scale  = STYLE_CONFIG["scale"]
    border = STYLE_CONFIG["border"]
    dark   = STYLE_CONFIG["dark_color"]        # #E63946 red
    light  = None if transparent else STYLE_CONFIG["light_color"]   # segno: None = transparent

    # ── Pass 1: render all dark modules in primary red ─────────────
    buf = io.BytesIO()
    qr.save(buf, kind="png", scale=scale, border=border,
            dark=dark, light=light)
    buf.seek(0)
    img = Image.open(buf).convert("RGBA")

    # ── Pass 2: repaint the 3 finder squares in accent blue ────────
    img = _colorise_finders(img, qr, scale, border)

    return img


def embed_logo(qr_img: Image.Image, logo_path: str) -> Image.Image:
    """
    Embed a logo at the center of the QR image.

    The logo is:
      • resized to STYLE_CONFIG["logo_ratio"] × QR side (≈ 20–25%)
      • placed on a white padded circle/square so modules beneath stay hidden
      • composited via alpha channel – no QR modules are distorted

    Scannability: error_correction=H can recover up to 30 % damage.
    A 22 % logo is safely within that budget.
    """
    if not os.path.exists(logo_path):
        print(f"⚠  Logo not found at '{logo_path}'. Skipping logo embedding.")
        return qr_img

    ratio  = STYLE_CONFIG["logo_ratio"]
    qr_w, qr_h = qr_img.size
    logo_size = int(min(qr_w, qr_h) * ratio)

    logo = Image.open(logo_path).convert("RGBA")

    # Maintain aspect ratio
    logo.thumbnail((logo_size, logo_size), Image.Resampling.LANCZOS)
    lw, lh = logo.size

    # White padded backing (adds a small halo so surrounding modules are readable)
    pad   = int(logo_size * 0.10)
    back  = Image.new("RGBA", (lw + pad * 2, lh + pad * 2), (255, 255, 255, 255))
    back.paste(logo, (pad, pad), mask=logo)

    # Center position
    bw, bh = back.size
    x = (qr_w - bw) // 2
    y = (qr_h - bh) // 2

    result = qr_img.copy()
    result.paste(back, (x, y), mask=back)
    return result


# ─────────────────────────────────────────────
# FINDER-PATTERN COLORISER
# ─────────────────────────────────────────────

def _colorise_finders(
    img: Image.Image,
    qr,
    scale: int,
    border: int,
) -> Image.Image:
    """
    Repaint the three 7×7 finder squares (top-left, top-right, bottom-left)
    with the accent blue color (#457B9D).

    We locate finders by their fixed grid positions (always at corners),
    convert to pixel coordinates, and flood-fill only the dark pixels inside
    each 7-module bounding box.
    """
    accent = _hex_to_rgba("#457B9D")
    px     = img.load()
    w, h   = img.size

    # Matrix side in modules (segno's matrix includes quiet zone)
    matrix_modules = qr.symbol_size()[0]   # total columns incl. border
    # The actual QR content starts at `border` modules from the edge

    # Finder top-left corners in MODULE coordinates (inside the quiet zone)
    # The 3 finders are always at positions (0,0), (cols-7, 0), (0, rows-7)
    content_size = matrix_modules - 2 * border   # pure QR data width in modules
    finders = [
        (border, border),                              # top-left
        (border + content_size - 7, border),           # top-right
        (border, border + content_size - 7),           # bottom-left
    ]

    primary_rgba = _hex_to_rgba(STYLE_CONFIG["dark_color"])

    for (mod_x, mod_y) in finders:
        # pixel rectangle for this 7×7 finder
        px_x1 = mod_x * scale
        px_y1 = mod_y * scale
        px_x2 = px_x1 + 7 * scale
        px_y2 = px_y1 + 7 * scale

        for py in range(px_y1, min(px_y2, h)):
            for pxx in range(px_x1, min(px_x2, w)):
                r, g, b, a = px[pxx, py]
                # only repaint pixels that are currently the primary red
                if a > 128 and _is_close_color((r, g, b), primary_rgba[:3], tol=60):
                    px[pxx, py] = accent

    return img


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def _hex_to_rgba(hex_color: str, alpha: int = 255) -> tuple:
    hex_color = hex_color.lstrip("#")
    r, g, b = (int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    return (r, g, b, alpha)


def _is_close_color(c1: tuple, c2: tuple, tol: int = 40) -> bool:
    return all(abs(a - b) <= tol for a, b in zip(c1, c2))


def _normalise_url(data: str) -> str:
    """Auto-prepend https:// if the data looks like a URL without a scheme."""
    stripped = data.strip()
    parsed   = urlparse(stripped)
    if parsed.scheme == "" and ("." in stripped or stripped.startswith("localhost")):
        stripped = "https://" + stripped
        print(f"⚠  Auto-corrected URL → {stripped}")
    return stripped


def _export_svg(qr, data: str, output_dir: str, return_bytes: bool):
    """Export QR as SVG (segno native, no Pillow)."""
    if return_bytes:
        buf = io.BytesIO()
        qr.save(buf, kind="svg",
                dark=STYLE_CONFIG["dark_color"],
                light=STYLE_CONFIG["light_color"],
                scale=4)
        buf.seek(0)
        return buf

    os.makedirs(output_dir, exist_ok=True)
    fname = _build_filename(data, "svg")
    path  = os.path.join(output_dir, fname)
    qr.save(path, kind="svg",
            dark=STYLE_CONFIG["dark_color"],
            light=STYLE_CONFIG["light_color"],
            scale=4)
    print(f"✅ SVG saved → {os.path.abspath(path)}")
    return os.path.abspath(path)


def _build_filename(data: str, ext: str, prefix: str = "") -> str:
    parsed  = urlparse(data)
    domain  = parsed.netloc.replace("www.", "") if parsed.netloc else "qr"
    domain  = "".join(c for c in domain if c.isalnum() or c in "-.")
    ts      = datetime.now().strftime("%H%M%S")
    return f"{prefix}{domain}_{ts}.{ext}"


def _save(img: Image.Image, data: str, output_dir: str, prefix: str = "") -> str:
    os.makedirs(output_dir, exist_ok=True)
    fname = _build_filename(data, "png", prefix)
    path  = os.path.join(output_dir, fname)
    img.save(path, format="PNG")
    print(f"✅ Saved → {os.path.abspath(path)}")
    return os.path.abspath(path)


# ─────────────────────────────────────────────
# CLI ENTRY POINT
# ─────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    print("=" * 55)
    print("  QR Code Generator  (powered by segno + Pillow)")
    print("=" * 55)

    # ── Get URL ───────────────────────────────────────────────────
    if len(sys.argv) > 1:
        link = sys.argv[1]
    else:
        link = input("\n🔗 Enter URL or data: ").strip()

    if not link:
        print("❌ No data provided. Exiting.")
        sys.exit(1)

    # ── Evolve flag ───────────────────────────────────────────────
    ev_input = input("\n🎨 Generate styled Evolve QR? (y/n) [default: n]: ").strip().lower()
    evolve   = ev_input in ("y", "yes")

    # ── Logo ──────────────────────────────────────────────────────
    logo = None
    if evolve:
        lp = input("\n🖼  Logo path (leave blank to skip): ").strip()
        if lp:
            logo = lp

    # ── Transparent background ────────────────────────────────────
    tr_input = input("\n🔲 Transparent background? (y/n) [default: n]: ").strip().lower()
    transparent = tr_input in ("y", "yes")

    # ── Output format ─────────────────────────────────────────────
    fmt_input = input("\n📄 Output format: png/svg [default: png]: ").strip().lower()
    fmt = fmt_input if fmt_input in ("svg", "png") else "png"

    print()

    path = generate_qr(
        data=link,
        evolve=evolve,
        logo_path=logo,
        transparent=transparent,
        output_format=fmt,
    )

    print(f"\n🎉 Done!  File → {path}")
