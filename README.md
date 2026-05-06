NavMate

NavMate is a real-time, screen-aware AI assistant that helps users understand and navigate any interface using natural language.

Press a hotkey, ask a question, and NavMate will analyze your screen and visually guide you with labeled overlays.

Features
Ask about anything on your screen
Press a hotkey and ask questions like:
“Where do I search?” or “How do I mute myself?”
Context-aware AI guidance
Uses Claude Vision to understand UI elements and provide step-by-step guidance
Visual overlay system
Highlights relevant UI components with bounding boxes and explanations
Global hotkeys
Trigger NavMate from anywhere (not just inside the app)
App-aware prompts
Adapts responses based on the active application (Chrome, Zoom, VS Code, etc.)
Architecture Overview

NavMate is built as a modular pipeline:

User → Hotkey → Screenshot → App Detection → AI (Claude Vision) → Overlay UI

Core components:

screenshot.py → captures screen or region
app_detector.py → detects active application
ai_client.py → sends image + prompt to Claude
overlay.py → renders visual guidance
input_dialog.py → user query input
Getting Started
1. Clone the repository
git clone https://github.com/yourusername/navmate.git
cd navmate
2. Install dependencies
pip install -r requirements.txt
3. Set your API key

Get your API key from Anthropic and set it:

Windows (PowerShell):

$env:ANTHROPIC_API_KEY="your_api_key_here"
4. Run the app
python main.py
Usage
Guide Mode
Press: Ctrl + Shift + H
Type a question
NavMate analyzes your screen and shows labeled guidance