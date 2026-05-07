"""
Unit tests for voice_input.py.

speech_recognition is mocked at the sys.modules level so no real microphone
or internet connection is required.  All worker logic is tested synchronously
by calling _worker directly; thread properties and non-blocking behaviour are
tested by patching threading.Thread.
"""

import os
import sys
import threading
import types
from unittest import mock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from voice_input import _worker, start_listening


# ---------------------------------------------------------------------------
# Exception types that mirror speech_recognition's public API
# ---------------------------------------------------------------------------

class _SR:
    WaitTimeoutError  = type("WaitTimeoutError",  (Exception,), {})
    UnknownValueError = type("UnknownValueError", (Exception,), {})
    RequestError      = type("RequestError",      (Exception,), {})


# ---------------------------------------------------------------------------
# Mock factory
# ---------------------------------------------------------------------------

def _make_sr(
    *,
    mic_raises=None,
    listen_raises=None,
    recognize_raises=None,
    recognize_result="hello world",
):
    """Return a minimal speech_recognition module substitute."""

    class Recognizer:
        def __init__(self):
            self.pause_threshold       = 0.0
            self.non_speaking_duration = 0.0

        def adjust_for_ambient_noise(self, source, duration=1.0):
            pass

        def listen(self, source, timeout=None, phrase_time_limit=None):
            if listen_raises is not None:
                raise listen_raises
            return object()

        def recognize_google(self, audio):
            if recognize_raises is not None:
                raise recognize_raises
            return recognize_result

    class Microphone:
        def __init__(self):
            if mic_raises is not None:
                raise mic_raises

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    return types.SimpleNamespace(
        Recognizer=Recognizer,
        Microphone=Microphone,
        WaitTimeoutError=_SR.WaitTimeoutError,
        UnknownValueError=_SR.UnknownValueError,
        RequestError=_SR.RequestError,
    )


# ---------------------------------------------------------------------------
# Synchronous test runner
# ---------------------------------------------------------------------------

def _run(sr_mock, *, timeout=8.0, phrase_time_limit=12.0):
    """
    Run _worker synchronously with the given sr mock.
    Returns (ready_called: bool, result: str|None, error: str|None).
    """
    ready  = []
    result = []
    error  = []

    with mock.patch.dict(sys.modules, {"speech_recognition": sr_mock}):
        _worker(
            on_ready  = lambda:   ready.append(True),
            on_result = lambda t: result.append(t),
            on_error  = lambda e: error.append(e),
            timeout=timeout,
            phrase_time_limit=phrase_time_limit,
        )

    return bool(ready), result[0] if result else None, error[0] if error else None


# ===========================================================================
# 1. Happy path
# ===========================================================================

class TestWorkerSuccess:
    def test_on_result_receives_transcribed_text(self):
        _, result, _ = _run(_make_sr(recognize_result="zoom in please"))
        assert result == "zoom in please"

    def test_on_ready_fires_on_success(self):
        ready, _, _ = _run(_make_sr())
        assert ready is True

    def test_on_error_not_called_on_success(self):
        _, _, error = _run(_make_sr())
        assert error is None

    def test_ready_fires_before_result(self):
        sequence = []
        with mock.patch.dict(sys.modules, {"speech_recognition": _make_sr()}):
            _worker(
                on_ready  = lambda:   sequence.append("ready"),
                on_result = lambda t: sequence.append("result"),
                on_error  = lambda e: None,
                timeout=8.0,
                phrase_time_limit=12.0,
            )
        assert sequence == ["ready", "result"]

    def test_exactly_one_result_and_zero_errors(self):
        results = []
        errors  = []
        with mock.patch.dict(sys.modules, {"speech_recognition": _make_sr()}):
            _worker(
                on_ready  = lambda:   None,
                on_result = lambda t: results.append(t),
                on_error  = lambda e: errors.append(e),
                timeout=8.0,
                phrase_time_limit=12.0,
            )
        assert len(results) == 1
        assert len(errors)  == 0


# ===========================================================================
# 2. Missing package
# ===========================================================================

class TestMissingSpeechRecognition:
    """sys.modules[key] = None causes 'import <key>' to raise ImportError."""

    def _run_without_sr(self):
        ready  = []
        result = []
        error  = []
        with mock.patch.dict(sys.modules, {"speech_recognition": None}):
            _worker(
                on_ready  = lambda:   ready.append(True),
                on_result = lambda t: result.append(t),
                on_error  = lambda e: error.append(e),
                timeout=8.0,
                phrase_time_limit=12.0,
            )
        return bool(ready), result[0] if result else None, error[0] if error else None

    def test_calls_on_error(self):
        _, _, error = self._run_without_sr()
        assert error is not None

    def test_error_message_mentions_pip_install(self):
        _, _, error = self._run_without_sr()
        assert "pip install" in error.lower()

    def test_on_ready_not_called(self):
        ready, _, _ = self._run_without_sr()
        assert ready is False

    def test_on_result_not_called(self):
        _, result, _ = self._run_without_sr()
        assert result is None


# ===========================================================================
# 3. Microphone unavailable
# ===========================================================================

class TestMicrophoneError:
    def test_os_error_calls_on_error(self):
        _, _, error = _run(_make_sr(mic_raises=OSError("no audio device")))
        assert error is not None

    def test_error_message_mentions_microphone(self):
        _, _, error = _run(_make_sr(mic_raises=OSError("no audio device")))
        assert "microphone" in error.lower()

    def test_on_ready_not_called_when_mic_fails(self):
        ready, _, _ = _run(_make_sr(mic_raises=OSError()))
        assert ready is False

    def test_on_result_not_called_when_mic_fails(self):
        _, result, _ = _run(_make_sr(mic_raises=OSError()))
        assert result is None


# ===========================================================================
# 4. Listen / capture errors
# ===========================================================================

class TestListenErrors:
    def test_timeout_calls_on_error(self):
        _, _, error = _run(_make_sr(listen_raises=_SR.WaitTimeoutError()))
        assert error is not None

    def test_timeout_message_mentions_no_speech(self):
        _, _, error = _run(_make_sr(listen_raises=_SR.WaitTimeoutError()))
        assert "speech" in error.lower() or "detected" in error.lower()

    def test_timeout_on_result_not_called(self):
        _, result, _ = _run(_make_sr(listen_raises=_SR.WaitTimeoutError()))
        assert result is None

    def test_on_ready_already_fired_before_timeout(self):
        # on_ready() is called before r.listen(), so it fires even when listen times out
        ready, _, _ = _run(_make_sr(listen_raises=_SR.WaitTimeoutError()))
        assert ready is True

    def test_generic_listen_exception_calls_on_error(self):
        _, _, error = _run(_make_sr(listen_raises=RuntimeError("hardware failure")))
        assert error is not None

    def test_generic_listen_error_message_contains_mic_error(self):
        _, _, error = _run(_make_sr(listen_raises=RuntimeError("hardware failure")))
        assert "mic" in error.lower() or "error" in error.lower()

    def test_on_ready_fired_before_generic_listen_exception(self):
        # Same principle: on_ready() precedes r.listen() in the source
        ready, _, _ = _run(_make_sr(listen_raises=RuntimeError("crash")))
        assert ready is True


# ===========================================================================
# 5. Transcription errors
# ===========================================================================

class TestTranscriptionErrors:
    def test_unknown_value_calls_on_error(self):
        _, _, error = _run(_make_sr(recognize_raises=_SR.UnknownValueError()))
        assert error is not None

    def test_unknown_value_message_mentions_understand(self):
        _, _, error = _run(_make_sr(recognize_raises=_SR.UnknownValueError()))
        assert "understand" in error.lower()

    def test_unknown_value_on_result_not_called(self):
        _, result, _ = _run(_make_sr(recognize_raises=_SR.UnknownValueError()))
        assert result is None

    def test_request_error_calls_on_error(self):
        _, _, error = _run(_make_sr(recognize_raises=_SR.RequestError("503")))
        assert error is not None

    def test_request_error_message_mentions_service(self):
        _, _, error = _run(_make_sr(recognize_raises=_SR.RequestError("503")))
        assert "service" in error.lower() or "unavailable" in error.lower()

    def test_request_error_on_result_not_called(self):
        _, result, _ = _run(_make_sr(recognize_raises=_SR.RequestError("down")))
        assert result is None

    def test_generic_transcription_exception_calls_on_error(self):
        _, _, error = _run(_make_sr(recognize_raises=ValueError("unexpected")))
        assert error is not None

    def test_generic_transcription_error_contains_exception_message(self):
        _, _, error = _run(_make_sr(recognize_raises=ValueError("boom")))
        assert "boom" in error

    def test_on_ready_fired_before_transcription_error(self):
        ready, _, _ = _run(_make_sr(recognize_raises=_SR.UnknownValueError()))
        assert ready is True


# ===========================================================================
# 6. Recognizer configuration
# ===========================================================================

class TestRecognizerConfiguration:
    def test_pause_threshold_and_non_speaking_duration(self):
        captured = []
        sr = _make_sr()
        orig = sr.Recognizer

        class CapturingRecognizer(orig):
            def __init__(self):
                super().__init__()
                captured.append(self)

        sr.Recognizer = CapturingRecognizer
        _run(sr)

        assert captured[0].pause_threshold       == 1.5
        assert captured[0].non_speaking_duration == 1.0

    def test_ambient_noise_calibration_duration(self):
        durations = []
        sr = _make_sr()
        orig = sr.Recognizer.adjust_for_ambient_noise

        def recording_calibrate(self, source, duration=1.0):
            durations.append(duration)
            return orig(self, source, duration=duration)

        sr.Recognizer.adjust_for_ambient_noise = recording_calibrate
        _run(sr)

        assert len(durations) == 1
        assert durations[0] == pytest.approx(0.3)

    def test_timeout_and_phrase_limit_forwarded_to_listen(self):
        calls = []
        sr = _make_sr()
        orig = sr.Recognizer.listen

        def recording_listen(self, source, timeout=None, phrase_time_limit=None):
            calls.append((timeout, phrase_time_limit))
            return orig(self, source, timeout=timeout, phrase_time_limit=phrase_time_limit)

        sr.Recognizer.listen = recording_listen
        _run(sr, timeout=5.0, phrase_time_limit=10.0)

        assert calls[0] == (5.0, 10.0)


# ===========================================================================
# 7. start_listening thread contract
# ===========================================================================

class TestStartListeningThread:
    def test_spawns_daemon_thread_named_mic_input(self):
        with mock.patch("voice_input.threading.Thread") as MockThread:
            MockThread.return_value = mock.MagicMock()
            start_listening(
                on_ready  = lambda:   None,
                on_result = lambda t: None,
                on_error  = lambda e: None,
            )
            _, kwargs = MockThread.call_args
        assert kwargs.get("daemon") is True
        assert kwargs.get("name")   == "mic-input"

    def test_returns_before_worker_fires_callbacks(self):
        """start_listening must return before the worker thread fires on_ready."""
        # Strategy: gate the worker behind an event.  Signal 'returned' only after
        # start_listening returns, then open the gate.  The callback checks whether
        # 'returned' was already set — no timestamp precision issues.
        may_proceed = threading.Event()
        returned    = threading.Event()   # set by main thread after start_listening returns
        callback_saw_return = [False]
        done = threading.Event()

        sr = _make_sr(recognize_result="x")
        orig_calibrate = sr.Recognizer.adjust_for_ambient_noise

        def gated_calibrate(self, source, duration=1.0):
            may_proceed.wait(timeout=5)   # hold here until main thread opens the gate
            return orig_calibrate(self, source, duration=duration)

        sr.Recognizer.adjust_for_ambient_noise = gated_calibrate

        def on_ready():
            callback_saw_return[0] = returned.is_set()
            done.set()

        with mock.patch.dict(sys.modules, {"speech_recognition": sr}):
            start_listening(
                on_ready  = on_ready,
                on_result = lambda t: None,
                on_error  = lambda e: None,
            )
            returned.set()    # record that start_listening has returned
            may_proceed.set() # open the gate — worker can now call on_ready

        done.wait(timeout=5.0)
        assert done.is_set(), "on_ready never fired"
        assert callback_saw_return[0], "on_ready fired before start_listening returned"

    def test_result_delivered_end_to_end(self):
        done   = threading.Event()
        result = [None]

        with mock.patch.dict(sys.modules, {"speech_recognition": _make_sr(recognize_result="find print button")}):
            start_listening(
                on_ready  = lambda:   None,
                on_result = lambda t: (result.__setitem__(0, t), done.set()),
                on_error  = lambda e: done.set(),
            )

        done.wait(timeout=5.0)
        assert result[0] == "find print button"

    def test_error_delivered_end_to_end(self):
        done  = threading.Event()
        error = [None]

        with mock.patch.dict(sys.modules, {
            "speech_recognition": _make_sr(recognize_raises=_SR.UnknownValueError())
        }):
            start_listening(
                on_ready  = lambda:   None,
                on_result = lambda t: done.set(),
                on_error  = lambda e: (error.__setitem__(0, e), done.set()),
            )

        done.wait(timeout=5.0)
        assert error[0] is not None
        assert "understand" in error[0].lower()
