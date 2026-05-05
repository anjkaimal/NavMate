# App-specific context injected into the system prompt to improve accuracy.
_APP_CONTEXTS: dict[str, str] = {
    "zoom": (
        "The user is in Zoom. Common UI elements: mute/unmute mic button (bottom-left toolbar), "
        "start/stop video button, share screen button, participants list button, chat panel button, "
        "reactions button, and the red 'End' button (bottom-right). The toolbar appears at the "
        "bottom of the Zoom window during an active meeting."
    ),
    "chrome": (
        "The user is in Google Chrome. Common UI elements: address bar / omnibox (top center), "
        "back button (top-left arrow), forward button, reload button, bookmark star icon, "
        "bookmarks bar, tab strip at top, new tab '+' button, extensions toolbar (puzzle icon), "
        "three-dot menu (top-right corner)."
    ),
    "vscode": (
        "The user is in Visual Studio Code. Common UI elements: activity bar (far-left icons for "
        "Explorer, Search, Source Control, Extensions, Run), side panel, editor tab strip, "
        "integrated terminal (bottom panel), status bar (very bottom), breadcrumbs bar, "
        "command palette opened with Ctrl+Shift+P."
    ),
    "generic": "",
}

_GUIDE_SCHEMA = """\
You must respond with ONLY valid JSON — no markdown fences, no commentary, nothing else.
The JSON must match this exact schema:
{
  "elements": [
    {
      "label": "<short name for the UI element>",
      "bounding_box": { "x": <int>, "y": <int>, "width": <int>, "height": <int> },
      "explanation": "<one sentence instruction for the user>"
    }
  ]
}
Bounding box coordinates are pixels relative to the top-left corner of the screenshot.
Return only the elements most relevant to the user's query. Maximum 6 elements."""

_EXPLAIN_SCHEMA = """\
You must respond with ONLY valid JSON — no markdown fences, no commentary, nothing else.
The JSON must match this exact schema:
{ "explanation": "<one or two sentences describing what this UI element does>" }"""


def get_system_prompt(app_key: str, mode: str) -> str:
    context = _APP_CONTEXTS.get(app_key, "")

    if mode == "guide":
        parts = [
            "You are a helpful desktop UI assistant. "
            "The user will share a screenshot and ask what to do. "
            "Identify the specific UI elements that answer their question and return their locations.",
        ]
        if context:
            parts.append(context)
        parts.append(_GUIDE_SCHEMA)
        return "\n\n".join(parts)

    if mode == "explain":
        parts = [
            "You are a helpful desktop UI assistant. "
            "The user will share a cropped screenshot of a single UI element. "
            "Explain what that element does in plain language.",
        ]
        if context:
            parts.append(context)
        parts.append(_EXPLAIN_SCHEMA)
        return "\n\n".join(parts)

    raise ValueError(f"Unknown prompt mode: {mode!r}")
