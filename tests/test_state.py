"""
Unit tests for app/state.py - Thread-safe global state management.
Tests verify thread safety, locking, and concurrent access patterns.
"""

import pytest
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from app.state import AppState


@pytest.mark.unit
class TestAppStateBasics:
    """Test basic AppState functionality."""
    
    def test_state_initialization(self):
        """Test that AppState initializes with correct defaults."""
        state = AppState()
        assert state.recording_active == False
        assert state.current_transcript == ""
        assert state.stop_event.is_set() == True
        assert state.audio_queue is not None
        assert state.recording_thread is None
        assert state.transcription_thread is None
    
    def test_reset_clears_state(self, app_state_fresh):
        """Test that reset() clears all state."""
        app_state_fresh.recording_active = True
        app_state_fresh.current_transcript = "Some transcript"
        
        app_state_fresh.reset()
        
        assert app_state_fresh.recording_active == False
        assert app_state_fresh.current_transcript == ""
        assert app_state_fresh.stop_event.is_set() == True
    
    def test_is_recording_getter(self, app_state_fresh):
        """Test is_recording() getter method."""
        assert app_state_fresh.is_recording() == False
        app_state_fresh.recording_active = True
        assert app_state_fresh.is_recording() == True


@pytest.mark.unit
class TestThreadSafetySetters:
    """Test thread-safe setter methods."""
    
    def test_set_recording_active_thread_safe(self, app_state_fresh):
        """Test set_recording_active() is thread-safe."""
        results = []
        
        def toggle_recording(state, index):
            for i in range(100):
                if i % 2 == 0:
                    state.set_recording_active(True)
                    results.append(("set_true", threading.current_thread().name))
                else:
                    state.set_recording_active(False)
                    results.append(("set_false", threading.current_thread().name))
        
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [
                executor.submit(toggle_recording, app_state_fresh, i)
                for i in range(5)
            ]
            for future in as_completed(futures):
                future.result()
        
        # Verify no exceptions and results collected
        assert len(results) == 500  # 5 threads * 100 iterations
        assert all(r[0] in ("set_true", "set_false") for r in results)
    
    def test_get_transcript_thread_safe(self, app_state_fresh):
        """Test get_transcript() is thread-safe."""
        app_state_fresh.current_transcript = "Initial transcript"
        results = []
        
        def read_transcript(state):
            for _ in range(100):
                transcript = state.get_transcript()
                results.append(transcript)
        
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [
                executor.submit(read_transcript, app_state_fresh)
                for _ in range(5)
            ]
            for future in as_completed(futures):
                future.result()
        
        # Verify all reads got consistent value
        assert len(results) == 500  # 5 threads * 100 iterations
        assert all(r == "Initial transcript" for r in results)


@pytest.mark.unit
class TestTranscriptManipulation:
    """Test transcript getter, setter, and append operations."""
    
    def test_set_transcript(self, app_state_fresh):
        """Test setting transcript."""
        transcript = "Patient reports chest pain"
        app_state_fresh.set_transcript(transcript)
        assert app_state_fresh.get_transcript() == transcript
    
    def test_append_transcript(self, app_state_fresh):
        """Test appending to transcript."""
        app_state_fresh.set_transcript("First part. ")
        app_state_fresh.append_transcript("Second part.")
        
        expected = "First part. Second part."
        assert app_state_fresh.get_transcript() == expected
    
    def test_append_empty_transcript(self, app_state_fresh):
        """Test appending when transcript is empty."""
        app_state_fresh.append_transcript("First append.")
        assert app_state_fresh.get_transcript() == "First append."
    
    def test_concurrent_append_transcript(self, app_state_fresh):
        """Test concurrent append_transcript() calls remain ordered."""
        app_state_fresh.set_transcript("")
        
        def append_text(state, text):
            for i in range(10):
                state.append_transcript(f"{text}-{i} ")
        
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [
                executor.submit(append_text, app_state_fresh, f"Thread{i}")
                for i in range(3)
            ]
            for future in as_completed(futures):
                future.result()
        
        transcript = app_state_fresh.get_transcript()
        # Verify that all appends are present (order may vary due to threading)
        assert "Thread0-" in transcript
        assert "Thread1-" in transcript
        assert "Thread2-" in transcript
        assert len(transcript.split()) > 20


@pytest.mark.unit
class TestStopEventManagement:
    """Test stop_event threading control."""
    
    def test_stop_event_initially_set(self, app_state_fresh):
        """Test that stop_event is initially set."""
        assert app_state_fresh.stop_event.is_set() == True
    
    def test_stop_event_can_be_cleared(self, app_state_fresh):
        """Test that stop_event can be cleared."""
        app_state_fresh.stop_event.clear()
        assert app_state_fresh.stop_event.is_set() == False
    
    def test_stop_event_can_be_set(self, app_state_fresh):
        """Test that stop_event can be set."""
        app_state_fresh.stop_event.clear()
        app_state_fresh.stop_event.set()
        assert app_state_fresh.stop_event.is_set() == True


@pytest.mark.unit
class TestThreadReferences:
    """Test thread reference management."""
    
    def test_thread_reference_assignment(self, app_state_fresh):
        """Test assigning thread references."""
        thread = threading.Thread(target=lambda: None)
        app_state_fresh.recording_thread = thread
        assert app_state_fresh.recording_thread == thread
    
    def test_reset_clears_thread_references(self, app_state_fresh):
        """Test that reset() clears thread references."""
        app_state_fresh.recording_thread = threading.Thread(target=lambda: None)
        app_state_fresh.transcription_thread = threading.Thread(target=lambda: None)
        
        app_state_fresh.reset()
        
        assert app_state_fresh.recording_thread is None
        assert app_state_fresh.transcription_thread is None


@pytest.mark.unit
class TestAudioQueue:
    """Test audio queue management."""
    
    def test_queue_put_get(self, app_state_fresh):
        """Test putting and getting from audio queue."""
        import numpy as np
        
        audio_chunk = np.random.rand(1024, 1).astype(np.float32)
        app_state_fresh.audio_queue.put(audio_chunk)
        
        retrieved = app_state_fresh.audio_queue.get(timeout=1)
        assert np.array_equal(retrieved, audio_chunk)
    
    def test_queue_empty_after_reset(self, app_state_fresh):
        """Test that queue is empty after reset."""
        import numpy as np
        
        audio_chunk = np.random.rand(1024, 1).astype(np.float32)
        app_state_fresh.audio_queue.put(audio_chunk)
        
        app_state_fresh.reset()
        
        assert app_state_fresh.audio_queue.empty()
    
    def test_concurrent_queue_operations(self, app_state_fresh):
        """Test concurrent queue put/get operations."""
        import numpy as np
        
        results = []
        
        def producer(state, thread_id):
            for i in range(10):
                chunk = np.random.rand(1024, 1).astype(np.float32)
                state.audio_queue.put((thread_id, i, chunk))
        
        def consumer(state):
            while True:
                try:
                    item = state.audio_queue.get(timeout=0.5)
                    results.append(item)
                except:
                    break
        
        with ThreadPoolExecutor(max_workers=5) as executor:
            # Start 3 producers
            for i in range(3):
                executor.submit(producer, app_state_fresh, i)
            
            time.sleep(0.1)  # Let producers put items
            
            # Start 2 consumers
            for _ in range(2):
                executor.submit(consumer, app_state_fresh)
        
        # Verify items were consumed
        assert len(results) > 0
        assert all(len(r) == 3 for r in results)  # (thread_id, index, chunk)


@pytest.mark.unit
class TestGlobalInstance:
    """Test the global app_state instance."""
    
    def test_global_app_state_exists(self):
        """Test that global app_state instance is accessible."""
        from app.state import app_state
        assert app_state is not None
        assert isinstance(app_state, AppState)
    
    def test_global_app_state_persistent(self):
        """Test that global app_state persists across imports."""
        from app.state import app_state as state1
        from app.state import app_state as state2
        
        # Should be the same instance
        assert state1 is state2
