from typing import Optional

_store: dict = {
    "screenshot_b64": None,
    "result": None,
    "query": None,
}


def save(screenshot_b64: str, result: list, query: str) -> None:
    _store["screenshot_b64"] = screenshot_b64
    _store["result"] = result
    _store["query"] = query


def load() -> tuple[Optional[str], Optional[list], Optional[str]]:
    return _store["screenshot_b64"], _store["result"], _store["query"]


def clear() -> None:
    _store["screenshot_b64"] = None
    _store["result"] = None
    _store["query"] = None


def has_data() -> bool:
    return _store["screenshot_b64"] is not None
