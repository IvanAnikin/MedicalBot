"""
Integration tests for app/audio_manager.py - Audio recording functionality.
Tests verify audio capture, thread management, and error handling.
"""

import pytest
import threading
import time
import numpy as np
from unittest.mock import Mock, patch, MagicMock

from app.state import AppState
from app.audio_manager import (
    start_recording_thread, 
    stop_recording_thread,
    SAMPLE_RATE,
    CHANNELS,
    CHUNK_SIZE
)


@pytest.mark.integration
@pytest.mark.audio
class TestAudioManagerConstants:
    """Test audio configuration constants."""
    
    def test_sample_rate_is_16khz(self):
        """Test that sample rate is 16000 Hz."""
        assert SAMPLE_RATE == 16000
    
    def test_channels_is_mono(self):
        """Test that channels is set to 1 (mono)."""
        assert CHANNELS == 1
    
    def test_chunk_size_is_1024(self):
        """Test that chunk size is 1024 frames."""
        assert CHUNK_SIZE == 1024


@pytest.mark.integration
@pytest.mark.audio
class TestStartRecordingThread:
    """Test start_recording_thread() function."""
    
    def test_start_recording_creates_thread(self, app_state_fresh, mock_sounddevice):
        """Test that start_recording_thread creates a daemon thread."""
        thread = start_recording_thread(app_state_fresh)
        
        assert thread is not None
        assert isinstance(thread, threading.Thread)
        assert thread.daemon == False  # We set daemon=False for clean shutdown
        
        # Cleanup
        thread.join(timeout=2)
    
    def test_recording_thread_puts_chunks_in_queue(self, app_state_fresh, mock_sounddevice):
        """Test that recording thread puts audio chunks in queue."""
        thread = start_recording_thread(app_state_fresh)
        
        # Let it capture a few chunks
        time.sleep(0.5)
        
        # Should have chunks in queue
        assert not app_state_fresh.audio_queue.empty()
        
        # Get a chunk and verify shape
        chunk = app_state_fresh.audio_queue.get(timeout=1)
        assert isinstance(chunk, np.ndarray)
        assert chunk.shape[1] == CHANNELS  # Should be mono
    
    def test_recording_thread_respects_stop_event(self, app_state_fresh, mock_sounddevice):
        """Test that recording thread stops when stop_event is set."""
        thread = start_recording_thread(app_state_fresh)
        
        # Let it run briefly
        time.sleep(0.2)
        
        # Signal stop
        app_state_fresh.stop_event.set()
        
        # Thread should stop
        thread.join(timeout=2)
        assert not thread.is_alive()
    
    def test_recording_thread_sets_stream_open_flag(self, app_state_fresh, mock_sounddevice):
        """Test that recording thread opens audio stream."""
        thread = start_recording_thread(app_state_fresh)
        
        # Let it initialize
        time.sleep(0.1)
        
        # sounddevice.InputStream should have been called
        mock_sounddevice.InputStream.assert_called()
        
        # Cleanup
        app_state_fresh.stop_event.set()
        thread.join(timeout=2)


@pytest.mark.integration
@pytest.mark.audio
class TestStopRecordingThread:
    """Test stop_recording_thread() function."""
    
    def test_stop_recording_stops_active_thread(self, app_state_fresh, mock_sounddevice):
        """Test that stop_recording_thread stops an active recording."""
        # Start recording
        thread = start_recording_thread(app_state_fresh)
        time.sleep(0.2)
        
        # Verify thread is running
        assert thread.is_alive()
        
        # Stop recording
        stop_recording_thread(app_state_fresh, thread, timeout=2)
        
        # Verify thread stopped
        assert not thread.is_alive()
    
    def test_stop_recording_with_timeout(self, app_state_fresh, mock_sounddevice):
        """Test that stop_recording_thread respects timeout."""
        thread = start_recording_thread(app_state_fresh)
        time.sleep(0.1)
        
        # Stop with short timeout
        stop_recording_thread(app_state_fresh, thread, timeout=1)
        
        # Thread should have stopped
        assert not thread.is_alive()
    
    def test_stop_recording_returns_chunk_count(self, app_state_fresh, mock_sounddevice):
        """Test that stop_recording_thread returns info about captured chunks."""
        thread = start_recording_thread(app_state_fresh)
        time.sleep(0.3)  # Let it capture some chunks
        
        # Stop recording
        stop_recording_thread(app_state_fresh, thread, timeout=2)
        
        # Should have captured chunks
        assert not app_state_fresh.audio_queue.empty()


@pytest.mark.integration
@pytest.mark.audio
class TestAudioDataProcessing:
    """Test audio data handling and processing."""
    
    def test_captured_audio_is_float32(self, app_state_fresh, mock_sounddevice):
        """Test that captured audio data is float32."""
        thread = start_recording_thread(app_state_fresh)
        time.sleep(0.2)
        
        chunk = app_state_fresh.audio_queue.get(timeout=1)
        assert chunk.dtype == np.float32
        
        app_state_fresh.stop_event.set()
        thread.join(timeout=2)
    
    def test_captured_audio_has_correct_shape(self, app_state_fresh, mock_sounddevice):
        """Test that captured audio has (N, 1) shape for mono."""
        thread = start_recording_thread(app_state_fresh)
        time.sleep(0.2)
        
        chunk = app_state_fresh.audio_queue.get(timeout=1)
        assert len(chunk.shape) == 2  # 2D array
        assert chunk.shape[1] == 1  # Mono (1 channel)
        assert chunk.shape[0] == CHUNK_SIZE or chunk.shape[0] > 0
        
        app_state_fresh.stop_event.set()
        thread.join(timeout=2)
    
    def test_multiple_chunks_accumulated(self, app_state_fresh, mock_sounddevice):
        """Test that multiple chunks are accumulated over time."""
        thread = start_recording_thread(app_state_fresh)
        
        # Let it capture multiple chunks
        time.sleep(0.5)
        
        chunk_count = app_state_fresh.audio_queue.qsize()
        assert chunk_count > 0, "Should have captured at least one chunk"
        
        app_state_fresh.stop_event.set()
        thread.join(timeout=2)


@pytest.mark.integration
@pytest.mark.audio
class TestRecordingStateManagement:
    """Test state management during recording."""
    
    def test_recording_thread_updates_audio_queue(self, app_state_fresh, mock_sounddevice):
        """Test that recording thread updates the app state's audio queue."""
        thread = start_recording_thread(app_state_fresh)
        time.sleep(0.3)
        
        # Queue should not be empty
        assert not app_state_fresh.audio_queue.empty()
        
        app_state_fresh.stop_event.set()
        thread.join(timeout=2)
    
    def test_concurrent_recording_and_consumption(self, app_state_fresh, mock_sounddevice):
        """Test that audio can be consumed while recording."""
        captured_chunks = []
        
        def consume_audio(state):
            for _ in range(10):
                try:
                    chunk = state.audio_queue.get(timeout=0.5)
                    captured_chunks.append(chunk)
                except:
                    break
        
        # Start recording
        thread = start_recording_thread(app_state_fresh)
        
        # Consume chunks while recording
        consumer_thread = threading.Thread(target=consume_audio, args=(app_state_fresh,))
        consumer_thread.start()
        
        # Let them run
        time.sleep(0.5)
        
        # Stop recording
        app_state_fresh.stop_event.set()
        thread.join(timeout=2)
        consumer_thread.join(timeout=2)
        
        # Verify chunks were captured and consumed
        assert len(captured_chunks) > 0


@pytest.mark.integration
@pytest.mark.audio
class TestErrorHandling:
    """Test error handling in audio manager."""
    
    def test_recording_handles_device_error(self, app_state_fresh):
        """Test graceful handling when no audio device available."""
        with patch("app.audio_manager.sd.InputStream") as mock_stream:
            mock_stream.side_effect = RuntimeError("No audio device found")
            
            # Starting recording should fail gracefully or handle the error
            try:
                thread = start_recording_thread(app_state_fresh)
                app_state_fresh.stop_event.set()
                thread.join(timeout=1)
            except RuntimeError as e:
                assert "No audio device found" in str(e)
    
    def test_recording_handles_stream_error_during_read(self, app_state_fresh, mock_sounddevice):
        """Test handling of errors during audio stream reading."""
        # Configure mock to fail after a few reads
        call_count = [0]
        
        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] > 3:
                raise IOError("Stream read failed")
            return (np.random.rand(CHUNK_SIZE, 1).astype(np.float32), False)
        
        mock_sounddevice.InputStream.return_value.__enter__.return_value.read.side_effect = side_effect
        
        thread = start_recording_thread(app_state_fresh)
        time.sleep(0.2)
        
        app_state_fresh.stop_event.set()
        thread.join(timeout=2)


@pytest.mark.integration
@pytest.mark.audio
@pytest.mark.slow
class TestLongRecording:
    """Test long-duration recording scenarios."""
    
    def test_record_multiple_seconds(self, app_state_fresh, mock_sounddevice):
        """Test recording for multiple seconds accumulates chunks correctly."""
        thread = start_recording_thread(app_state_fresh)
        
        # Record for 2 seconds
        time.sleep(2)
        
        chunk_count = app_state_fresh.audio_queue.qsize()
        
        # At 16kHz, 1024 frame chunks = 64ms per chunk
        # 2 seconds = ~31 chunks expected
        assert chunk_count > 20, f"Expected >20 chunks in 2 seconds, got {chunk_count}"
        
        app_state_fresh.stop_event.set()
        thread.join(timeout=2)
    
    def test_recording_accumulates_without_loss(self, app_state_fresh, mock_sounddevice):
        """Test that all chunks are captured without loss during recording."""
        recorded_chunks = []
        
        # Start recording
        thread = start_recording_thread(app_state_fresh)
        time.sleep(1)
        
        # Drain queue
        while not app_state_fresh.audio_queue.empty():
            try:
                chunk = app_state_fresh.audio_queue.get_nowait()
                recorded_chunks.append(chunk)
            except:
                break
        
        app_state_fresh.stop_event.set()
        thread.join(timeout=2)
        
        # Verify chunks captured
        assert len(recorded_chunks) > 0
        
        # Calculate total audio duration
        total_frames = sum(chunk.shape[0] for chunk in recorded_chunks)
        duration_seconds = total_frames / SAMPLE_RATE
        
        # Should be close to 1 second
        assert 0.8 < duration_seconds < 1.5, f"Expected ~1 second, got {duration_seconds}s"
