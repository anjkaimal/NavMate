"""
Text-to-speech for NavMate.

Each utterance is synthesised in a dedicated child Python process so the
pyttsx3/SAPI COM objects are fully isolated from Qt's COM apartment and event
loop.  A daemon queue thread serialises requests so overlapping speak() calls
never produce simultaneous audio.
"""

import queue
import subprocess
import sys
import tempfile
import threading
import os

from logger import get_logger

log = get_logger(__name__)

_RATE   = 165   # words per minute
_VOLUME = 1.0

_q: queue.SimpleQueue = queue.SimpleQueue()
_started = False
_lock    = threading.Lock()


def speak(text: str) -> None:
    """Queue text for immediate asynchronous speech.  Returns at once."""
    if not text or not text.strip():
        return
    _ensure_started()
    #_q.put(text)
    try:
        _q.get_nowait()
    except queue.Empty:
        pass
    _q.put(text)


# ── Internal ────────────────────────────────────────────────────────────────

def _ensure_started() -> None:
    global _started
    with _lock:
        if not _started:
            _start_worker()

def _start_worker() -> None:
    global _started
    def run():
        global _started
        log.debug("TTS: worker thread ready")
        try:
            while True:
                text = _q.get()
                log.debug(f"TTS speak: {text!r}")
                _speak_subprocess(text)
        except Exception as exc:
            log.error(f"TTS worker crashed: {exc}", exc_info=True)
        finally:
            # Allow restart on next speak() call
            with _lock:
                _started = False

    threading.Thread(target=run, daemon=True, name="tts").start()
    _started = True

def _speak_subprocess(text: str) -> None:
    """Run pyttsx3 in a child process via a temp file to avoid quoting bugs."""
    # Write the script to a temp file — no shell-quoting issues with text content
    script = f"""\
import pyttsx3
e = pyttsx3.init()
e.setProperty('rate', {_RATE})
e.setProperty('volume', {_VOLUME})
e.say({text!r})
e.runAndWait()
"""
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.py', delete=False, encoding='utf-8'
        ) as f:
            f.write(script)
            tmp = f.name

        subprocess.run(
            [sys.executable, tmp],
            creationflags=subprocess.CREATE_NO_WINDOW,
            timeout=15,   # tighter timeout — 30s is too long
        )
    except subprocess.TimeoutExpired:
        log.warning("TTS subprocess timed out")
    except Exception as exc:
        log.warning(f"TTS subprocess error ({exc}) — trying PowerShell fallback")
        _speak_powershell(text)
    finally:
        if tmp:
            try:
                os.unlink(tmp)
            except OSError:
                pass

def _speak_powershell(text: str) -> None:
    """Last-resort fallback via Windows SAPI through PowerShell."""
    safe = text.replace("'", " ").replace('"', " ")
    try:
        subprocess.run(
            ["powershell", "-WindowStyle", "Hidden", "-Command",
             f"(New-Object -ComObject SAPI.SpVoice).Speak('{safe}')"],
            creationflags=subprocess.CREATE_NO_WINDOW,
            timeout=15,
        )
    except Exception as exc:
        log.warning(f"TTS PowerShell fallback error: {exc}")