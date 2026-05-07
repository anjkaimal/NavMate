NavMate

NavMate is a real-time, screen-aware AI assistant that helps users understand and navigate any interface using natural language.

A small floating dock sits in the corner of your screen at all times. Click Ask a Question, type what you need help with, and NavMate will analyze your screen and visually guide you with labeled overlays.

Features
Ask about anything on your screen
Click the dock and ask questions like:
“Where do I search?” or “How do I mute myself?”
Context-aware AI guidance
Uses Claude Vision to understand UI elements and provide step-by-step guidance
Visual overlay system
Highlights relevant UI components with bounding boxes and explanations
Always-present dock
The NavMate assistant dock stays visible in the corner of your screen — no shortcuts to remember
App-aware prompts
Adapts responses based on the active application (Chrome, Zoom, VS Code, etc.)
Architecture Overview

NavMate is built as a modular pipeline:

User → Dock → Screenshot → App Detection → AI (Claude Vision) → Overlay UI

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
Click "🔍 Ask a Question" in the dock
Type a question
NavMate analyzes your screen and shows labeled guidance