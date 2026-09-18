"""Regenerate the terminal-logo assets from the source image.

    python scripts/render_logo_assets.py [path/to/logo.png] [--width 30]

Writes into src/zerotrace/ui/assets/:
  logo.png        optimized copy, sent as-is via the Kitty/iTerm2 image protocols
  mark.uni.txt    the mark as a Unicode shading ramp (" ░▒▓█"), one char per cell
  mark.ascii.txt  the same mark as an ASCII density ramp (" .:-=+*#%@")
  mark.small.*    the same two at a narrower width, for 60-column terminals

Coverage is supersampled and averaged, so edges and the white cut-outs survive as
mid-tones; a hard black/white threshold loses the eyes, mouth and horn detail.

The source art is a black silhouette with white cut-out details on a transparent
background, so "ink" is *opaque and dark*: the silhouette becomes white blocks in the
terminal and the cut-outs stay empty. Colour is applied by the renderer (a single white
style), never baked in here, so NO_COLOR and redirected output still behave.

Needs Pillow (a dev extra). The runtime package never imports it: this is a maintainer
step, and the generated assets are committed.
"""
import sys
from pathlib import Path

from PIL import Image

ASSETS = Path(__file__).resolve().parent.parent / "src" / "zerotrace" / "ui" / "assets"
DEFAULT_SOURCE = ASSETS / "logo2.png"

_PNG_MAX_SIDE = 240
_CELL_ASPECT = 2.0   # a terminal cell is about twice as tall as it is wide
_OPAQUE = 128        # alpha at or above this counts as part of the artwork
_DARK = 140          # luminance below this is the silhouette (the ink)

_SHADE_RAMP = " ░▒▓█"            # lightest -> darkest; all four exist in CP437
_ASCII_RAMP = " .:-=+*#%@"       # the classic density ramp


def coverage(img: Image.Image, width: int, supersample: int = 4) -> list[list[float]]:
    """Per-cell ink coverage in 0..1, computed by supersampling then averaging.

    "Ink" is opaque *and* dark: the mark is a black silhouette whose white details are
    cut-outs, so averaging preserves the eyes, mouth and horn edges as mid-tones instead
    of collapsing them to a hard threshold (which is what made the first pass look wrong).
    """
    img = img.convert("RGBA")
    bbox = img.getchannel("A").getbbox()
    if bbox:
        img = img.crop(bbox)
    src_w, src_h = img.size
    rows = max(round(src_h * width / src_w / _CELL_ASPECT), 1)

    fine = img.resize((width * supersample, rows * supersample), Image.LANCZOS)
    pixels = fine.load()

    grid = []
    for cell_y in range(rows):
        line = []
        for cell_x in range(width):
            ink = 0
            for dy in range(supersample):
                for dx in range(supersample):
                    r, g, b, a = pixels[cell_x * supersample + dx, cell_y * supersample + dy]
                    luma = 0.2126 * r + 0.7152 * g + 0.0722 * b
                    ink += 1 if (a >= _OPAQUE and luma < _DARK) else 0
            line.append(ink / (supersample * supersample))
        grid.append(line)
    return grid


def _ramp_art(grid: list[list[float]], ramp: str) -> str:
    """Map coverage to a character ramp (lightest first), trimming trailing blanks."""
    last = len(ramp) - 1
    lines = []
    for row in grid:
        line = "".join(ramp[min(last, int(value * len(ramp)))] for value in row)
        lines.append(line.rstrip())
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines) + "\n"


def to_shaded(grid: list[list[float]]) -> str:
    """Unicode shading ramp. All four blocks are CP437 characters, so this also renders
    on a legacy Windows console once the codepage is UTF-8 or 437."""
    return _ramp_art(grid, _SHADE_RAMP)


def to_ascii(grid: list[list[float]]) -> str:
    return _ramp_art(grid, _ASCII_RAMP)


def write_png(img: Image.Image) -> None:
    copy = img.convert("RGBA")
    copy.thumbnail((_PNG_MAX_SIDE, _PNG_MAX_SIDE), Image.LANCZOS)
    copy.save(ASSETS / "logo.png", optimize=True)


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    width = 30
    for arg in argv:
        if arg.startswith("--width="):
            width = int(arg.split("=", 1)[1])
    source = Path(args[0]) if args else DEFAULT_SOURCE
    if not source.is_file():
        print(f"no such image: {source}", file=sys.stderr)
        return 2

    img = Image.open(source)
    grid = coverage(img, width)
    for name, text in (("mark.uni.txt", to_shaded(grid)), ("mark.ascii.txt", to_ascii(grid))):
        (ASSETS / name).write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {name}: {len(text.splitlines())} lines x {width} cols")
    write_png(img)
    print(f"wrote logo.png (max side {_PNG_MAX_SIDE}px)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
