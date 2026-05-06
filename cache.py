from typing import Optional

_store: dict = {
    "screenshot_b64": None,
    "result": None,
    "query": None,
    "ai_img_w": 0,   # pixel width of the image that was sent to the AI
    "ai_img_h": 0,   # pixel height of the image that was sent to the AI
}

# overrites the store with new data
def save(
    screenshot_b64: str,
    result: list,
    query: str,
    ai_img_w: int = 0,
    ai_img_h: int = 0,
) -> None:
    _store["screenshot_b64"] = screenshot_b64
    _store["result"] = result
    _store["query"] = query
    _store["ai_img_w"] = ai_img_w
    _store["ai_img_h"] = ai_img_h

# returns image, user query, dimensions as a tuple
def load() -> tuple[Optional[str], Optional[list], Optional[str], int, int]:
    return (
        _store["screenshot_b64"],
        _store["result"],
        _store["query"],
        _store["ai_img_w"],
        _store["ai_img_h"],
    )

# resets main fields
def clear() -> None:
    _store["screenshot_b64"] = None
    _store["result"] = None
    _store["query"] = None


def has_data() -> bool:
    return _store["screenshot_b64"] is not None
