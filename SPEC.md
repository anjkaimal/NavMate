# NavMate — Implementation Spec

**Goal:** A Windows desktop app with a persistent floating dock that lets users ask questions about their screen. It captures a screenshot, sends it with the user's query to a multimodal AI, and renders a semi-transparent overlay with labeled bounding boxes pointing to relevant UI elements.

---

## Table of Contents

1. [Project Structure](#1-project-structure)
2. [Dependencies](#2-dependencies)
3. [Data Contracts](#3-data-contracts)
4. [Step-by-Step Implementation Plan](#4-step-by-step-implementation-plan)
5. [Module Responsibilities](#5-module-responsibilities)
6. [App-Specific Tuning](#6-app-specific-tuning)
7. [Explain Mode](#7-explain-mode)
8. [Bonus Features](#8-bonus-features)
9. [Error Handling Strategy](#9-error-handling-strategy)
10. [Open Questions / Decisions](#10-open-questions--decisions)

---

## 1. Project Structure

```
NavMate/
├── main.py              # Entry point: shows dock + starts Qt app loop
├── assistant_dock.py    # Persistent floating dock (Ask / Explain Mode buttons)
├── screenshot.py        # Screen capture → base64 PNG
├── ai_client.py         # Sends screenshot + query to AI; parses JSON response
├── prompts.py           # System prompts + app-specific tuning templates
├── overlay.py           # PyQt6 fullscreen semi-transparent overlay
├── input_dialog.py      # Small floating text-input widget for the user query
├── explain_mode.py      # Mouse tracking + explain-on-hover logic
├── cache.py             # In-memory cache for last screenshot + last AI result
├── app_detector.py      # Reads active window title → selects prompt template
├── logger.py            # Rotating file logger for debug output
├── config.py            # Constants (API model, overlay colours, etc.)
├── requirements.txt
└── SPEC.md              # This file
```

---

## 2. Dependencies

| Package | Purpose |
|---|---|
| `PyQt6` | Overlay window, input dialog, bounding-box painting |
| `mss` | Fast cross-monitor screenshot capture |
| `keyboard` | *(optional)* Legacy hotkey support — not used in default flow |
| `anthropic` | Claude Vision API (primary AI backend) |
| `Pillow` | Image resizing / base64 encoding before API call |
| `pywin32` | `win32gui.GetForegroundWindow()` → active app title |
| `pynput` | Mouse position tracking for Explain Mode |

Install with:
```
pip install PyQt6 mss keyboard anthropic Pillow pywin32 pynput
```

---

## 3. Data Contracts

### 3.1 AI Response — Strict JSON Schema

The AI must return **only** this JSON, no markdown, no commentary:

```json
{
  "elements": [
    {
      "label": "Mute button",
      "bounding_box": { "x": 120, "y": 450, "width": 40, "height": 40 },
      "explanation": "Click this to mute your microphone in Zoom"
    }
  ]
}
```

| Field | Type | Notes |
|---|---|---|
| `label` | string | Short display name drawn above the box |
| `bounding_box.x` | int | Pixels from left edge of screen |
| `bounding_box.y` | int | Pixels from top edge of screen |
| `bounding_box.width` | int | Box width in pixels |
| `bounding_box.height` | int | Box height in pixels |
| `explanation` | string | Instruction shown near the box on the overlay |

### 3.2 Explain Mode Response

```json
{
  "explanation": "This is the Share Screen button. Click it to present your display to other participants."
}
```

---

## 4. Step-by-Step Implementation Plan

### Step 1 — Scaffold & Config (`config.py`, `requirements.txt`)

- Define all constants: API model name, overlay alpha, box colour, font size, max screenshot dimension, log file path.
- Load `ANTHROPIC_API_KEY` from environment variable (never hardcode).

### Step 2 — Logger (`logger.py`)

- `logging.handlers.RotatingFileHandler` → `navmate_debug.log` (max 2 MB, 3 backups).
- Single `get_logger(name)` helper used across all modules.
- Log level `DEBUG` to file, `WARNING` to stderr.

### Step 3 — Screenshot Capture (`screenshot.py`)

- Use `mss` to capture the primary monitor (`sct.monitors[1]`).
- Resize image so longest edge ≤ 1920 px (avoids oversized API payloads) using Pillow.
- Return both the raw `PIL.Image` and its base64-encoded PNG string.
- Expose `capture_region(x, y, w, h)` for Explain Mode (crops a specific area).

### Step 4 — Active App Detection (`app_detector.py`)

- Call `win32gui.GetWindowText(win32gui.GetForegroundWindow())` to get the active window title.
- Map title patterns to an app key: `"zoom"` → `"zoom"`, `"chrome"` / `"chromium"` → `"chrome"`, default → `"generic"`.
- Return the app key; consumed by `prompts.py`.

### Step 5 — Prompt Templates (`prompts.py`)

- `get_system_prompt(app_key, mode)` returns a tailored string.
  - **`mode="guide"`** (main guide flow): instruct the AI to identify elements relevant to the user's query and return strict JSON.
  - **`mode="explain"`** (Explain Mode): instruct the AI to describe the cropped region concisely.
- App-specific context injected into system prompt:
  - `zoom`: "Common UI elements include: mute/unmute mic button (bottom-left), start/stop video, share screen, participants list, chat panel, end meeting (red button bottom-right)."
  - `chrome`: "Common UI elements include: address/omnibox bar, back/forward buttons, reload, bookmarks bar, tab strip, extensions toolbar, three-dot menu."
  - `generic`: neutral description.
- Require the model to return **only** the JSON schema defined in §3; any non-JSON output should be treated as an error.

### Step 6 — AI Client (`ai_client.py`)

- Single async-ready function `query_ai(screenshot_b64, user_query, app_key, mode)`.
- Builds the `anthropic.Anthropic` client.
- Constructs the message with:
  - System prompt from `prompts.py`.
  - User message containing the base64 image + the user's query text.
- Uses `client.messages.create(model=..., max_tokens=1024, ...)`.
- Parses response text with `json.loads()`; on `JSONDecodeError` logs the raw text and raises a typed `AIResponseError`.
- Validates that `elements` key exists and each element has required fields; raises `AIResponseError` on schema mismatch.

### Step 7 — Input Dialog (`input_dialog.py`)

- `QueryDialog(QWidget)`: a small frameless, always-on-top window.
  - Semi-transparent background, single `QLineEdit`, a "Go" button, and an "×" button.
  - Appears centered on screen when the dock's Ask button is clicked.
  - Emits a `query_submitted(str)` signal on Enter or "Go".
  - Closes itself on Escape or "×".
- Keep it lightweight; no large chrome.

### Step 8 — Overlay Rendering (`overlay.py`)

- `OverlayWindow(QWidget)`: fullscreen, `Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool`.
- Set window background to `rgba(0, 0, 0, 100)` (semi-transparent black).
- `paintEvent`: for each element in the AI result:
  - Draw a colored rectangle (`QPen`, width 3, bright color e.g. `#00FF99`).
  - Draw the `label` text above the box in a legible font with a dark drop shadow.
  - Draw the `explanation` text below the box, word-wrapped if long.
- "Try Again" button (bottom-right corner, only visible when overlay is showing).
- "Close" hint: `Esc` key or clicking outside any box dismisses the overlay.
- `show_elements(elements: list[dict])` method populates and shows the window.
- `clear()` hides and resets it.

### Step 9 — Assistant Dock (`assistant_dock.py`)

- `AssistantDock(QWidget)`: frameless, always-on-top, persistent in the bottom-right corner.
- Emits `ask_requested` when the Ask button is clicked.
- Emits `explain_toggled` when the Explain Mode button is clicked.
- Draggable; position persisted to `.navmate_dock_pos.json`.
- Collapses to a slim header bar via the ▼ button.

### Step 10 — Explain Mode (`explain_mode.py`)

- `pynput.mouse.Listener` tracks the current mouse position globally, stored in a thread-safe variable.
- When Explain Mode is active, a 2-second dwell timer fires automatically after the cursor stays still:
  1. Grab mouse position `(mx, my)`.
  2. Crop a region of ±150 px around the cursor using `screenshot.capture_region`.
  3. Call `ai_client.query_ai(cropped_b64, "What does this do?", app_key, mode="explain")`.
  4. Display a small tooltip-style `QLabel` near the cursor with the returned explanation.
- Moving the cursor more than 25 px resets the dwell timer.
- Tooltip auto-dismisses after 6 seconds.

### Step 11 — Cache (`cache.py`)

- Simple module-level dict: `_cache = {"screenshot": None, "result": None, "query": None}`.
- `save(screenshot_b64, result, query)` / `load()` / `clear()`.
- The overlay's "Try Again" button calls `cache.load()` and re-invokes `ai_client.query_ai` without taking a new screenshot.

### Step 12 — Main Entry Point (`main.py`)

- Create `QApplication`.
- Instantiate all modules.
- Wire signals:
  - `AssistantDock.ask_requested` → show `QueryDialog`.
  - `AssistantDock.explain_toggled` → toggle `ExplainMode`, update dock appearance.
  - `QueryDialog.query_submitted` → capture screenshot → detect app → call AI → cache result → show `OverlayWindow`.
  - "Try Again" button → load cache → call AI → update overlay.
- Show dock; start `pynput` mouse listener thread.
- `app.exec()` — blocks until quit.

### Step 13 — Packaging (optional)

- `PyInstaller --onefile --windowed main.py` to produce a standalone `.exe`.
- Include `.env` lookup or prompt user to set `ANTHROPIC_API_KEY` in their environment.

---

## 5. Module Responsibilities

```
main.py ──────────────────────── orchestrator, event wiring
  ├── assistant_dock.py ───────── persistent floating dock (always visible)
  ├── input_dialog.py ─────────── collects user query
  ├── screenshot.py ──────────── captures full screen or region
  ├── app_detector.py ─────────── returns active app key
  ├── prompts.py ──────────────── returns tuned system prompt
  ├── ai_client.py ────────────── talks to Claude, returns parsed elements
  ├── overlay.py ──────────────── draws fullscreen annotated overlay
  ├── explain_mode.py ─────────── tracks mouse, serves hover explanations
  ├── cache.py ────────────────── stores last screenshot + result
  └── logger.py ───────────────── debug logging across all modules
```

---

## 6. App-Specific Tuning

Prompt biasing is implemented in `prompts.py` by prepending a context block to the system prompt before the JSON schema instruction.

| App Key | Trigger (window title contains) | Bias Added to Prompt |
|---|---|---|
| `zoom` | "zoom" | Toolbar layout, mute position, share screen, end meeting |
| `chrome` | "chrome" or "chromium" | Omnibox, tab bar, back/forward, extensions, three-dot menu |
| `vscode` | "visual studio code" | Explorer panel, editor tabs, terminal, source control |
| `generic` | (default) | No extra bias; generic UI vocabulary |

Future apps can be added by extending the `APP_CONTEXTS` dict in `prompts.py` — no changes elsewhere needed.

---

## 7. Explain Mode

| Aspect | Detail |
|---|---|
| Toggle | Click "💡 Explain Mode" in the dock |
| Visual indicator | Dock button turns red; hint "Hover 2 s over anything" appears |
| Trigger | Hold cursor still over any UI element for 2 seconds |
| Region captured | ±150 px bounding box around cursor |
| AI mode | `mode="explain"` → returns single `explanation` string |
| Display | Tooltip `QLabel` near cursor, 6-second auto-dismiss |
| Exit | Click "🛑 Stop Explaining" in the dock |

---

## 8. Bonus Features

| Feature | Module | Notes |
|---|---|---|
| Screenshot cache | `cache.py` | Last screenshot kept in memory; reused by Try Again |
| "Try Again" button | `overlay.py` | Renders in overlay; re-sends cached screenshot + same query |
| Debug logging | `logger.py` | Rotating file log, structured messages with timestamps |
| Resize before upload | `screenshot.py` | Caps longest edge at 1920 px, reduces API latency + cost |

---

## 9. Error Handling Strategy

| Failure | Handling |
|---|---|
| No `ANTHROPIC_API_KEY` | Crash at startup with a clear `RuntimeError` message |
| AI returns non-JSON | Log raw response, show user-facing dialog "AI returned an unexpected response" |
| AI returns malformed schema | Log details, show "Could not parse AI result" message, allow Try Again |
| Screenshot fails | Log + show "Screenshot capture failed" message |
| Network timeout | Catch `anthropic.APIConnectionError`, show retry prompt |
| Dock position file unreadable | Fall back to default bottom-right position silently |

---

## 10. Open Questions / Decisions

| # | Question | Current Decision |
|---|---|---|
| 1 | PyQt6 vs Tkinter for overlay? | **PyQt6** — easier alpha transparency, proper always-on-top, richer painting API |
| 2 | AI backend: Claude vs OpenAI Vision? | **Claude** (anthropic SDK) — already available; swap is easy via `ai_client.py` |
| 3 | How to handle multi-monitor setups? | Capture primary monitor (`sct.monitors[1]`) for now; extend later |
| 4 | Should overlay intercept mouse clicks to guide user? | No click-through for now; user clicks after reading instructions |
| 5 | API key storage? | Environment variable only; no `.env` file committed |
| 6 | Packaging format? | Single `.exe` via PyInstaller as stretch goal |
