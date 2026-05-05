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
