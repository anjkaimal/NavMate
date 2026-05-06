# App-specific context injected into the system prompt to improve accuracy.
_APP_CONTEXTS: dict[str, str] = {
    "zoom": (
        "The user is in Zoom. Common UI elements: mute/unmute mic button (bottom-left toolbar), "
        "start/stop video button, share screen button, participants list button, chat panel button, "
        "reactions button, and the red 'End' button (bottom-right). The toolbar appears at the "
        "bottom of the Zoom window during an active meeting."
    ),
    "chrome": (
        "The user is in Google Chrome. Common UI elements: address bar / omnibox (top center, "
        "a long white input bar spanning most of the width), back button (top-left arrow), "
        "forward button, reload button, bookmark star icon, bookmarks bar, tab strip at top, "
        "new tab '+' button, extensions toolbar (puzzle icon), three-dot menu (top-right corner). "
        "IMPORTANT: On the Chrome New Tab page the Google Search input field is a text box "
        "labeled 'Search Google or type a URL' or 'Ask Google' — it sits BELOW the Google "
        "logo/doodle image and is visually distinct from the decorative logo. Do NOT confuse "
        "the Google logo, doodle image, or decorative artwork with the actual search input field. "
        "The search input is always a rectangular text box you can click and type into."
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
Bounding box coordinates are pixels relative to the top-left corner of the screenshot image you received.
Return only the elements most relevant to the user's query. Maximum 6 elements.
If the image region shown does not contain any UI elements relevant to the query, return: { "elements": [] }"""

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
