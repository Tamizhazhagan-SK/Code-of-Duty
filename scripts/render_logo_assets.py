"""Regenerate the tiered terminal-logo assets from a source image.

Usage:
    python scripts/render_logo_assets.py path/to/logo.png

Writes src/zerotrace/ui/assets/{logo.png, logo.ans, logo.txt}:
  logo.png  optimized/downsized copy, sent as-is via Kitty/iTerm2 image protocols
  logo.ans  truecolor Unicode half-block art (2 source pixel rows per cell)
  logo.txt  plain ASCII ramp art, no color codes, no unicode

Needs Pillow: `.venv\\Scripts\\python.exe -m pip install -e ".[dev]"`. The
runtime package (src/zerotrace/ui/logo.py) never imports Pillow -- this script
is a one-off maintainer step, not something that runs on a user's machine.
"""
import sys
from pathlib import Path

from PIL import Image

ASSETS = Path(__file__).resolve().parent.parent / "src" / "zerotrace" / "ui" / "assets"
_RAMP = " .:-=+*#%@"
_PNG_MAX_SIDE = 240
_ART_WIDTH = 34
_CELL_ASPECT = 2.0  # terminal cells are roughly twice as tall as they are wide
_TRANSPARENT = 16   # alpha below this is treated as "no pixel here"


def _resize_for_halfblocks(img: Image.Image, width: int) -> Image.Image:
    src_w, src_h = img.size
    cell_rows = max(round(src_h * width / src_w / _CELL_ASPECT), 1)
    return img.resize((width, cell_rows * 2))


def _resize_for_text(img: Image.Image, width: int) -> Image.Image:
    src_w, src_h = img.size
    height = max(round(src_h * width / src_w / _CELL_ASPECT), 1)
    return img.resize((width, height))


def _write_png(img: Image.Image) -> None:
    small = img.copy()
    small.thumbnail((_PNG_MAX_SIDE, _PNG_MAX_SIDE))
    small.save(ASSETS / "logo.png", format="PNG", optimize=True)


def _write_ansi(img: Image.Image) -> None:
    art = _resize_for_halfblocks(img.convert("RGBA"), _ART_WIDTH)
    w, h = art.size
    pixels = art.load()
    lines = []
    for y in range(0, h, 2):
        line = []
        for x in range(w):
            top = pixels[x, y]
            bottom = pixels[x, y + 1] if y + 1 < h else (0, 0, 0, 0)
            if top[3] < _TRANSPARENT and bottom[3] < _TRANSPARENT:
                line.append(" ")
            elif bottom[3] < _TRANSPARENT:
                line.append(f"\033[38;2;{top[0]};{top[1]};{top[2]}m\u2580\033[0m")
            elif top[3] < _TRANSPARENT:
                line.append(f"\033[38;2;{bottom[0]};{bottom[1]};{bottom[2]}m\u2584\033[0m")
            else:
                line.append(f"\033[38;2;{top[0]};{top[1]};{top[2]}m"
                            f"\033[48;2;{bottom[0]};{bottom[1]};{bottom[2]}m\u2580\033[0m")
        lines.append("".join(line))
    (ASSETS / "logo.ans").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_ascii(img: Image.Image) -> None:
    art = _resize_for_text(img.convert("LA"), _ART_WIDTH)
    w, h = art.size
    pixels = art.load()
    lines = []
    for y in range(h):
        line = []
        for x in range(w):
            luma, alpha = pixels[x, y]
            if alpha < _TRANSPARENT:
                line.append(" ")
            else:
                line.append(_RAMP[(255 - luma) * (len(_RAMP) - 1) // 255])
        lines.append("".join(line).rstrip())
    (ASSETS / "logo.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__)
        return 2
    source = Path(argv[0])
    if not source.is_file():
        print(f"no such file: {source}", file=sys.stderr)
        return 1
    ASSETS.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as img:
        img.load()
        _write_png(img.convert("RGBA"))
        _write_ansi(img)
        _write_ascii(img)
    print(f"wrote {ASSETS / 'logo.png'}, {ASSETS / 'logo.ans'}, {ASSETS / 'logo.txt'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
