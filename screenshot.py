import base64
import io

import mss
from PIL import Image

from config import SCREENSHOT_MAX_DIMENSION
from logger import get_logger

log = get_logger(__name__)


def capture_screen() -> tuple[Image.Image, str]:
    """Capture the primary monitor. Returns (PIL Image, base64 PNG string)."""
    with mss.mss() as sct:
        monitor = sct.monitors[1]
        raw = sct.grab(monitor)
        img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
    log.debug(f"Captured screen: {img.size}")
    img = _resize_if_needed(img)
    return img, _to_base64(img)


def capture_screen_raw() -> Image.Image:
    """Capture the primary monitor at native physical resolution (no resize)."""
    with mss.mss() as sct:
        monitor = sct.monitors[1]
        raw = sct.grab(monitor)
        img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
    log.debug(f"Raw capture: {img.size}")
    return img


def capture_screen_tiles(
    n_cols: int = 2,
    n_rows: int = 2,
    overlap_pct: float = 0.15,
) -> tuple[list[dict], int, int]:
    """
    Capture the full screen and split it into a grid of overlapping tiles.

    Each tile dict has:
        b64        – base64 PNG ready to send to the AI (possibly resized)
        offset_x   – left edge of this tile in full physical image coords
        offset_y   – top edge of this tile in full physical image coords
        tile_scale – ratio (physical_tile_width / ai_image_width)
                     used to remap AI bounding boxes back to physical coords

    Returns (tiles, full_physical_width, full_physical_height).
    """
    full = capture_screen_raw()
    W, H = full.size
    tile_w = W // n_cols
    tile_h = H // n_rows
    ox = int(tile_w * overlap_pct)
    oy = int(tile_h * overlap_pct)

    tiles: list[dict] = []
    for row in range(n_rows):
        for col in range(n_cols):
            # Crop bounds — extended by the overlap margin on every side
            x1 = max(0, col * tile_w - ox)
            y1 = max(0, row * tile_h - oy)
            x2 = min(W, (col + 1) * tile_w + ox)
            y2 = min(H, (row + 1) * tile_h + oy)

            # Core bounds — the non-overlapping zone this tile "owns".
            # An element is credited to this tile only if its centre falls here.
            # Using half-open intervals on interior edges ensures every screen
            # pixel belongs to exactly one tile's core with no gaps or overlaps.
            core_x1 = col * tile_w
            core_y1 = row * tile_h
            core_x2 = W if col == n_cols - 1 else (col + 1) * tile_w
            core_y2 = H if row == n_rows - 1 else (row + 1) * tile_h

            crop      = full.crop((x1, y1, x2, y2))
            phys_w    = crop.width
            resized   = _resize_if_needed(crop)
            ai_w      = resized.width

            tiles.append({
                "b64":        _to_base64(resized),
                "offset_x":   x1,
                "offset_y":   y1,
                "tile_scale": phys_w / ai_w,
                # Core ownership zone (physical screen coords)
                "core_x1":    core_x1,
                "core_y1":    core_y1,
                "core_x2":    core_x2,
                "core_y2":    core_y2,
                # Full-screen dimensions so _query_tile can detect last col/row
                "_full_w":    W,
                "_full_h":    H,
            })
            log.debug(
                f"Tile [{row},{col}] ({x1},{y1})–({x2},{y2})"
                f"  phys {phys_w}×{crop.height}  ai {ai_w}×{resized.height}"
            )

    return tiles, W, H


def capture_region(x: int, y: int, width: int, height: int) -> tuple[Image.Image, str]:
    """Capture a specific pixel region of the screen."""
    region = {"left": x, "top": y, "width": width, "height": height}
    with mss.mss() as sct:
        raw = sct.grab(region)
        img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
    log.debug(f"Captured region ({x},{y},{width},{height}): {img.size}")
    return img, _to_base64(img)


def _resize_if_needed(img: Image.Image) -> Image.Image:
    w, h = img.size
    longest = max(w, h)
    if longest <= SCREENSHOT_MAX_DIMENSION:
        return img
    scale = SCREENSHOT_MAX_DIMENSION / longest
    new_size = (int(w * scale), int(h * scale))
    log.debug(f"Resizing from {img.size} to {new_size}")
    return img.resize(new_size, Image.LANCZOS)


def _to_base64(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.standard_b64encode(buf.getvalue()).decode("utf-8")
