"""
Text-to-speech for NavMate.

Primary path: edge-tts (Microsoft neural voices, free, internet required) played
back via pygame — both run in an isolated child process to avoid COM apartment
conflicts with Qt.

Fallbacks (in order): pyttsx3 SAPI5, PowerShell SAPI.

A daemon queue thread serialises requests so overlapping speak() calls never
produce simultaneous audio.
"""

import os
import queue
import subprocess
import sys
import tempfile
import threading

from logger import get_logger

log = get_logger(__name__)

_VOICE  = "en-US-AriaNeural"   # edge-tts neural voice
_RATE   = "-10%"               # slightly slower than default for clarity
_VOLUME = "+0%"
_PYTTS_RATE = 165              # pyttsx3 fallback rate (words per minute)

_q: queue.SimpleQueue = queue.SimpleQueue()
_started = False
_lock    = threading.Lock()


def speak(text: str) -> None:
    """Queue text for immediate asynchronous speech.  Returns at once."""
    if not text or not text.strip():
        return
    _ensure_started()
    # Drop any pending utterance — latest instruction wins.
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

    def run() -> None:
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
            with _lock:
                _started = False   # allow restart on next speak()

    threading.Thread(target=run, daemon=True, name="tts").start()
    _started = True


def _speak_subprocess(text: str) -> None:
    """Synthesise and play in a child process (edge-tts → pyttsx3 fallback)."""
    script = f"""\
import asyncio, os, sys, tempfile

async def _main():
    tmp = None
    try:
        import pygame
        import edge_tts
        communicate = edge_tts.Communicate({text!r}, voice={_VOICE!r}, rate={_RATE!r}, volume={_VOLUME!r})
        fd, tmp = tempfile.mkstemp(suffix=".mp3")
        os.close(fd)
        await communicate.save(tmp)
        pygame.mixer.init()
        pygame.mixer.music.load(tmp)
        pygame.mixer.music.play()
        clock = pygame.time.Clock()
        while pygame.mixer.music.get_busy():
            clock.tick(20)
        pygame.mixer.quit()
    except Exception as exc:
        print(f"edge-tts/pygame failed: {{exc}}", file=sys.stderr)
        try:
            import pyttsx3
            e = pyttsx3.init()
            e.setProperty("rate", {_PYTTS_RATE})
            e.setProperty("volume", 1.0)
            e.say({text!r})
            e.runAndWait()
        except Exception as exc2:
            print(f"pyttsx3 failed: {{exc2}}", file=sys.stderr)
    finally:
        if tmp:
            try:
                os.unlink(tmp)
            except OSError:
                pass

asyncio.run(_main())
"""

    tmp_script = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(script)
            tmp_script = f.name

        result = subprocess.run(
            [sys.executable, tmp_script],
            creationflags=subprocess.CREATE_NO_WINDOW,
            capture_output=True,
            timeout=30,
        )
        if result.returncode != 0:
            stderr = result.stderr.decode(errors="replace").strip()
            log.warning(f"TTS subprocess exited {result.returncode}: {stderr}")
            if stderr:
                _speak_powershell(text)

    except subprocess.TimeoutExpired:
        log.warning("TTS subprocess timed out")
    except Exception as exc:
        log.warning(f"TTS subprocess error ({exc}) — trying PowerShell fallback")
        _speak_powershell(text)
    finally:
        if tmp_script:
            try:
                os.unlink(tmp_script)
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
