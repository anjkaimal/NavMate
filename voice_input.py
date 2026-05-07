"""
Microphone capture and speech-to-text for NavMate query input.

Uses the SpeechRecognition library with Google's free Web Speech API.
Runs entirely on a daemon thread; all three callbacks fire from that thread,
so callers must route them back to the Qt main thread via signals.

Requires:  pip install SpeechRecognition pyaudio
"""

import threading
from typing import Callable

from logger import get_logger

log = get_logger(__name__)


def start_listening(
    on_ready:  Callable[[], None],
    on_result: Callable[[str], None],
    on_error:  Callable[[str], None],
    timeout: float = 8.0,
    phrase_time_limit: float = 12.0,
) -> None:
    """
    Open the default microphone and transcribe the next utterance.

    on_ready  — called once ambient-noise calibration is done and we're live
    on_result — called with the transcribed string on success
    on_error  — called with a short user-facing message on any failure
    """
    threading.Thread(
        target=_worker,
        args=(on_ready, on_result, on_error, timeout, phrase_time_limit),
        daemon=True,
        name="mic-input",
    ).start()


def _worker(
    on_ready: Callable,
    on_result: Callable,
    on_error:  Callable,
    timeout: float,
    phrase_time_limit: float,
) -> None:
    try:
        import speech_recognition as sr
    except ImportError:
        on_error("Missing package — run: pip install SpeechRecognition pyaudio")
        return

    r = sr.Recognizer()
    r.pause_threshold       = 1.5   # seconds of silence that ends a phrase
    r.non_speaking_duration = 1.0   # must be ≤ pause_threshold
    r.energy_threshold      = 200   # lower = picks up quieter voices

    try:
        mic = sr.Microphone()
    except OSError as exc:
        on_error(f"No microphone found: {exc}")
        return

    try:
        with mic as source:
            r.adjust_for_ambient_noise(source, duration=0.3)
            on_ready()
            audio = r.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)
    except sr.WaitTimeoutError:
        on_error("No speech detected — try again")
        return
    except Exception as exc:
        on_error(f"Mic error: {exc}")
        return

    try:
        text = r.recognize_google(audio)
        on_result(text)
    except sr.UnknownValueError:
        on_error("Couldn't understand — please try again")
    except sr.RequestError as exc:
        on_error(f"Speech service unavailable: {exc}")
    except Exception as exc:
        log.error(f"Transcription error: {exc}", exc_info=True)
        on_error(str(exc))
