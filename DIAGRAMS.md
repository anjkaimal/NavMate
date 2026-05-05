# NavMate — Architecture & Tech Stack Diagrams

---

## 1. Tech Stack

```mermaid
mindmap
  root((NavMate))
    UI Layer
      PyQt6
        Fullscreen Overlay
        Input Dialog
        Tooltip Widget
    Input
      keyboard
        Global Hotkeys
      pynput
        Mouse Tracking
    Screen Capture
      mss
        Full Screen
        Region Crop
      Pillow
        Resize
        Base64 Encode
    AI
      Anthropic SDK
        Claude Vision
        Strict JSON Response
    OS Integration
      pywin32
        Active Window Title
        App Detection
    Utilities
      logging
        Rotating File Log
      json
        Response Parsing
```

---

## 2. Module Dependency Graph

```mermaid
graph TD
    main([main.py]) --> hotkey[hotkey.py]
    main --> input_dialog[input_dialog.py]
    main --> overlay[overlay.py]
    main --> explain_mode[explain_mode.py]
    main --> cache[cache.py]

    hotkey -->|fires event| main

    input_dialog -->|query_submitted signal| main

    main --> screenshot[screenshot.py]
    main --> app_detector[app_detector.py]
    main --> ai_client[ai_client.py]

    ai_client --> prompts[prompts.py]
    app_detector --> prompts

    overlay --> cache
    explain_mode --> screenshot
    explain_mode --> ai_client

    subgraph Core Pipeline
        screenshot
        app_detector
        prompts
        ai_client
    end

    subgraph Qt UI
        input_dialog
        overlay
    end

    subgraph System
        hotkey
        explain_mode
    end

    logger[logger.py] -.->|used by all| main
    logger -.-> ai_client
    logger -.-> overlay
    logger -.-> screenshot
    config[config.py] -.->|constants| main
    config -.-> overlay
    config -.-> ai_client
    config -.-> hotkey
```

---

## 3. Main Flow — Sequence Diagram

```mermaid
sequenceDiagram
    actor User
    participant HK as hotkey.py
    participant Main as main.py
    participant Dialog as input_dialog.py
    participant SS as screenshot.py
    participant AD as app_detector.py
    participant AI as ai_client.py
    participant OV as overlay.py
    participant Cache as cache.py

    User->>HK: Ctrl+Shift+H
    HK->>Main: invoke on Qt thread
    Main->>Dialog: show()
    User->>Dialog: types query + Enter
    Dialog->>Main: query_submitted("How do I mute?")
    Main->>SS: capture_screen()
    SS-->>Main: (image, base64_png)
    Main->>AD: get_active_app()
    AD-->>Main: "zoom"
    Main->>AI: query_ai(base64, query, "zoom", mode="guide")
    Note over AI: Sends image + prompt<br/>to Claude Vision API
    AI-->>Main: [{label, bounding_box, explanation}, ...]
    Main->>Cache: save(screenshot, result, query)
    Main->>OV: show_elements(elements)
    OV-->>User: Fullscreen overlay with boxes
    User->>OV: Esc / click
    OV->>Main: closed
```

---

## 4. Explain Mode — Sequence Diagram

```mermaid
sequenceDiagram
    actor User
    participant HK as hotkey.py
    participant EM as explain_mode.py
    participant SS as screenshot.py
    participant AI as ai_client.py
    participant OV as overlay.py

    User->>HK: Ctrl+Shift+E
    HK->>EM: toggle_explain_mode()
    EM-->>User: Status label "Explain Mode ON"

    User->>EM: moves mouse over UI element
    EM->>EM: track_position(mx, my)

    User->>HK: Ctrl+Shift+H (while hovering)
    HK->>EM: explain_at_cursor()
    EM->>SS: capture_region(mx-150, my-150, 300, 300)
    SS-->>EM: cropped base64 image
    EM->>AI: query_ai(cropped, "What does this do?", app, mode="explain")
    AI-->>EM: {"explanation": "This is the Share Screen button..."}
    EM->>OV: show_tooltip(explanation, mx, my)
    OV-->>User: Tooltip near cursor (6s auto-dismiss)
```

---

## 5. App-Specific Prompt Tuning — Decision Tree

```mermaid
flowchart TD
    A[Get foreground window title] --> B{Contains 'zoom'?}
    B -- Yes --> C[app_key = zoom\nBias: mute button, share screen,\nend meeting, participants, chat]
    B -- No --> D{Contains 'chrome'\nor 'chromium'?}
    D -- Yes --> E[app_key = chrome\nBias: omnibox, tabs, back/forward,\nextensions, three-dot menu]
    D -- No --> F{Contains\n'visual studio code'?}
    F -- Yes --> G[app_key = vscode\nBias: explorer panel, editor tabs,\nterminal, source control]
    F -- No --> H[app_key = generic\nNo extra bias]

    C --> I[prompts.get_system_prompt\napp_key, mode]
    E --> I
    G --> I
    H --> I

    I --> J[AI Client sends\ntuned system prompt\n+ screenshot + query]
```

---

## 6. Overlay Rendering — Component Layout

```mermaid
graph TB
    subgraph OverlayWindow["OverlayWindow — Fullscreen Semi-transparent Layer"]
        direction TB
        A["🟩 Bounding Box\n(bright green QPen, width 3)"]
        B["Label text above box\n(white, dark drop shadow)"]
        C["Explanation text below box\n(yellow, word-wrapped)"]
        D["Try Again button\n(bottom-right corner)"]
        E["Esc to dismiss hint\n(bottom-center, small grey text)"]
    end

    F[AI Response Elements] -->|show_elements list| OverlayWindow
    G[User presses Esc\nor clicks outside box] -->|clear| H[Overlay hidden]
    D -->|clicked| I[cache.load → ai_client.query_ai → redraw]
```

---

## 7. Data Flow — Screenshot to Overlay

```mermaid
flowchart LR
    A([Screen]) -->|mss capture| B[Raw PIL Image\nfull resolution]
    B -->|Pillow resize\nmax 1920px| C[Resized PIL Image]
    C -->|base64 encode| D[PNG base64 string]
    D -->|anthropic SDK\nmessages.create| E[Claude Vision API]
    E -->|response.content| F[Raw JSON string]
    F -->|json.loads + validate| G[List of Element Dicts]
    G -->|show_elements| H([Overlay Window])

    style E fill:#d4a,color:#fff
    style H fill:#0a8,color:#fff
```
