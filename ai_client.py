import json
from typing import Union

import anthropic

# config values for Anthropic API access and model behavior
from config import ANTHROPIC_API_KEY, AI_MODEL, AI_MAX_TOKENS
# builds system prompts tailored to the app and mode
from prompts import get_system_prompt
# centralized logger for debugging and observability
from logger import get_logger

log = get_logger(__name__)


# cached singleton client to avoid re-instantiating Anthropic client repeatedly
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
    mode='guide'   → returns list of element dicts
    mode='explain' → returns dict with 'explanation' key
    """
    system_prompt = get_system_prompt(app_key, mode)
    client = _get_client()

    log.debug(f"AI request: mode={mode} app={app_key} query='{user_query[:80]}'")

    # send multimodal request of image and text
    message = client.messages.create(
        model=AI_MODEL,
        max_tokens=AI_MAX_TOKENS,
        system=system_prompt,
        messages=[
            {
                "role": "user",
                "content": [
                    # screenshot input
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": screenshot_b64,
                        },
                    },
                    # user query
                    {"type": "text", "text": user_query},
                ],
            }
        ],
    )

    # extracts raw text response
    raw = message.content[0].text
    log.debug(f"Raw AI response ({len(raw)} chars): {raw[:300]}")

    # parse JSON output from model
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        log.error(f"JSON parse failed. Raw: {raw}")
        raise AIResponseError(f"AI returned non-JSON output: {exc}") from exc

    if mode == "guide":
        if not isinstance(parsed.get("elements"), list):
            raise AIResponseError(f"Missing or invalid 'elements' list in: {parsed}")
        for el in parsed["elements"]:
            _validate_element(el)
        log.debug(f"Parsed {len(parsed['elements'])} elements")
        return parsed["elements"]

    if mode == "explain":
        if not isinstance(parsed.get("explanation"), str):
            raise AIResponseError(f"Missing 'explanation' string in: {parsed}")
        return parsed

    raise AIResponseError(f"Unknown mode: {mode!r}")


# validates structure of a single UI element returned by the AI
def _validate_element(el: dict) -> None:
    for field in ("label", "bounding_box", "explanation"):
        if field not in el:
            raise AIResponseError(f"Element missing field '{field}': {el}")
    bb = el["bounding_box"]
    for dim in ("x", "y", "width", "height"):
        if dim not in bb or not isinstance(bb[dim], (int, float)):
            raise AIResponseError(f"bounding_box missing/invalid '{dim}': {bb}")
