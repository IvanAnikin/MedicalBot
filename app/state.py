"""
Global application state for recording and transcription management.
Thread-safe state container for recording control and transcript storage.
"""

import threading
import queue
from typing import Optional


class AppState:
    """Global application state."""

    def __init__(self):
        self.recording_active: bool = False
        self.stop_event: threading.Event = threading.Event()
        # By default the stop_event is set (meaning "not recording") so
        # callers can check is_set() to determine there is no active
        # recording. Tests and other code expect this to be True initially.
        self.stop_event.set()
        # Use a bounded queue to avoid unbounded memory growth when producers
        # (recording threads) run faster than consumers in tests or edge cases.
        # A maxsize of 1024 keeps recent audio while limiting memory use.
        self.audio_queue: queue.Queue = queue.Queue(maxsize=1024)
        self.recording_thread: Optional[threading.Thread] = None
        self.transcription_thread: Optional[threading.Thread] = None
        self.current_transcript: str = ""
        self._lock = threading.Lock()

    def reset(self):
        """Reset state to initial values."""
        with self._lock:
            self.recording_active = False
            # Ensure stop_event signals "stopped" after a reset
            self.stop_event.set()
            self.current_transcript = ""
            # Clear queue
            while not self.audio_queue.empty():
                try:
                    self.audio_queue.get_nowait()
                except queue.Empty:
                    break
            # Clear any thread references
            self.recording_thread = None
            self.transcription_thread = None

    def set_recording_active(self, active: bool):
        """Set recording state."""
        with self._lock:
            self.recording_active = active

    def is_recording(self) -> bool:
        """Check if recording is active."""
        with self._lock:
            return self.recording_active

    def set_transcript(self, transcript: str):
        """Update current transcript."""
        with self._lock:
            self.current_transcript = transcript

    def get_transcript(self) -> str:
        """Get current transcript."""
        with self._lock:
            return self.current_transcript

    def append_transcript(self, text: str):
        """Append text to current transcript."""
        with self._lock:
            self.current_transcript += text


# Global state instance
app_state = AppState()
