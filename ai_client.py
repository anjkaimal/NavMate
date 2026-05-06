import json
from typing import Union

import anthropic

from config import ANTHROPIC_API_KEY, AI_MODEL, AI_MAX_TOKENS
from prompts import get_system_prompt
from logger import get_logger

log = get_logger(__name__)

_client: anthropic.Anthropic | None = None


class AIResponseError(Exception):
    pass


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        if not ANTHROPIC_API_KEY:
            raise RuntimeError(
                "ANTHROPIC_API_KEY environment variable is not set. "
                "Set it before running NavMate."
            )
        _client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _client


def query_ai(
    screenshot_b64: str,
    user_query: str,
    app_key: str,
    mode: str = "guide",
) -> Union[list, dict]:
    """
    Send a screenshot + query to Claude Vision and return parsed AI data.
    mode='guide'   -> returns list of normalised element dicts
    mode='explain' -> returns dict with 'explanation' key

    All guide elements are normalised to internal format on the way out:
        bounding_box: {x, y, width, height}   (converted from bbox if needed)
        voice_instruction: str                 (unified from any legacy field)
    """
    system_prompt = get_system_prompt(app_key, mode)
    client = _get_client()

    log.debug(f"AI request: mode={mode} app={app_key} query='{user_query[:80]}'")

    message = client.messages.create(
        model=AI_MODEL,
        max_tokens=AI_MAX_TOKENS,
        system=system_prompt,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": screenshot_b64,
                        },
                    },
                    {"type": "text", "text": user_query},
                ],
            }
        ],
    )

    raw = message.content[0].text.strip()
    log.debug(f"Raw AI response ({len(raw)} chars): {raw[:300]}")

    # Empty response: treat as "no elements for this tile" rather than an error.
    if not raw:
        log.debug("AI returned empty response — treating as no elements for this tile")
        return [] if mode == "guide" else {"explanation": ""}

    # Strip markdown fences (```json … ```) the model sometimes adds.
    if raw.startswith("```"):
        lines = raw.splitlines()
        inner = [l for l in lines[1:] if l.strip() != "```"]
        raw = "\n".join(inner).strip()

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        log.error(f"JSON parse failed. Raw: {raw}")
        raise AIResponseError(f"AI returned non-JSON output: {exc}") from exc

    if mode == "guide":
        if not isinstance(parsed.get("elements"), list):
            raise AIResponseError(f"Missing or invalid 'elements' list in: {parsed}")
        normalised = [_normalise_element(el) for el in parsed["elements"]]
        log.debug(f"Parsed {len(normalised)} elements")
        return normalised

    if mode == "explain":
        if not isinstance(parsed.get("explanation"), str):
            raise AIResponseError(f"Missing 'explanation' string in: {parsed}")
        return parsed

    raise AIResponseError(f"Unknown mode: {mode!r}")


def _normalise_element(el: dict) -> dict:
    """
    Validate and normalise a single AI element to the internal format:
        {label, bounding_box: {x,y,width,height}, voice_instruction}

    Accepts both the current schema (bbox with x_min/y_min/x_max/y_max +
    voice_instruction) and legacy schemas (bounding_box + instruction/explanation).
    Raises AIResponseError on any structural violation.
    """
    if "label" not in el:
        raise AIResponseError(f"Element missing 'label': {el}")

    # ── Bounding box ──────────────────────────────────────────────────────
    if "bbox" in el and "bounding_box" not in el:
        # New format: {x_min, y_min, x_max, y_max}
        bbox = el["bbox"]
        for k in ("x_min", "y_min", "x_max", "y_max"):
            if k not in bbox or not isinstance(bbox[k], (int, float)):
                raise AIResponseError(f"bbox missing/invalid '{k}': {bbox}")
        x_min, y_min = float(bbox["x_min"]), float(bbox["y_min"])
        x_max, y_max = float(bbox["x_max"]), float(bbox["y_max"])
        if x_max <= x_min or y_max <= y_min:
            raise AIResponseError(f"bbox has zero/negative area: {bbox}")
        el = {
            **el,
            "bounding_box": {
                "x":      round(x_min),
                "y":      round(y_min),
                "width":  round(x_max - x_min),
                "height": round(y_max - y_min),
            },
        }
    elif "bounding_box" in el:
        bb = el["bounding_box"]
        for dim in ("x", "y", "width", "height"):
            if dim not in bb or not isinstance(bb[dim], (int, float)):
                raise AIResponseError(f"bounding_box missing/invalid '{dim}': {bb}")
        if bb["width"] <= 0 or bb["height"] <= 0:
            raise AIResponseError(f"bounding_box has zero/negative area: {bb}")
    else:
        raise AIResponseError(f"Element missing 'bbox' or 'bounding_box': {el}")

    # ── Voice instruction ─────────────────────────────────────────────────
    voice = (
        el.get("voice_instruction")
        or el.get("instruction")
        or el.get("explanation")
        or ""
    )
    el = {**el, "voice_instruction": voice}

    return el
