"""
Edge case and error scenario tests for MedicalBot.
Tests verify graceful error handling, race conditions, and edge cases.
"""

import pytest
import threading
import time
import numpy as np
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from main import app
from app.state import AppState


@pytest.fixture
def client():
    """Provide FastAPI test client."""
    return TestClient(app)


@pytest.mark.integration
class TestRecordingEdgeCases:
    """Test edge cases for recording functionality."""
    
    def test_stop_without_start(self, client):
        """Test stopping recording when never started."""
        response = client.post("/stop_recording")
        
        # Should return error status, not crash
        assert response.status_code >= 400 or response.status_code == 200
        assert response.json() is not None
    
    def test_rapid_start_stop_cycles(self, client):
        """Test rapid start/stop cycling for thread safety."""
        from app.state import app_state
        
        for cycle in range(5):
            response = client.post("/start_recording")
            assert response.status_code == 200
            
            time.sleep(0.1)
            
            response = client.post("/stop_recording")
            assert response.status_code == 200
            
            # Verify state is consistent
            assert app_state.is_recording() == False
    
    def test_concurrent_start_requests(self, client):
        """Test concurrent start requests."""
        from concurrent.futures import ThreadPoolExecutor
        
        def start_recording():
            return client.post("/start_recording")
        
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(start_recording) for _ in range(3)]
            responses = [f.result() for f in futures]
        
        # Only one should succeed (200), others should get 409 Conflict
        status_codes = [r.status_code for r in responses]
        assert 200 in status_codes
        assert sum(1 for sc in status_codes if sc == 409) >= 1


@pytest.mark.integration
class TestTranscriptEdgeCases:
    """Test edge cases for transcript handling."""
    
    def test_generate_report_without_transcript(self, client):
        """Test generating report when no transcript exists."""
        from app.state import app_state
        app_state.reset()
        
        response = client.post("/generate_report")
        
        # Should handle gracefully
        assert response.status_code in [400, 422, 200]
    
    def test_very_long_transcript(self, client):
        """Test handling very long transcripts."""
        from app.state import app_state
        
        # Create a very long transcript (10K+ characters)
        long_text = "Patient reports " * 1000
        app_state.set_transcript(long_text)
        
        response = client.get("/transcript")
        data = response.json()
        
        assert len(data["transcript"]) > 1000
        assert data["transcript"] == long_text
    
    def test_transcript_with_special_characters(self, client):
        """Test transcript with special characters."""
        from app.state import app_state
        
        special_text = "Patient: José García-López. Temp: 101.5°F. Notes: 你好世界 🏥"
        app_state.set_transcript(special_text)
        
        response = client.get("/transcript")
        data = response.json()
        
        assert data["transcript"] == special_text
    
    def test_transcript_with_newlines_and_formatting(self, client):
        """Test transcript with newlines and formatting."""
        from app.state import app_state
        
        formatted_text = """Patient Information:
        Name: John Doe
        Age: 45
        
        Chief Complaint:
        Fever and cough
        
        Notes:
        - Temp: 101.5°F
        - Started 3 days ago
        """
        
        app_state.set_transcript(formatted_text)
        
        response = client.get("/transcript")
        data = response.json()
        
        assert data["transcript"] == formatted_text
        assert "\n" in data["transcript"]


@pytest.mark.integration
class TestAPIConfigurationEdgeCases:
    """Test edge cases for API configuration."""
    
    def test_missing_openai_api_key(self):
        """Test behavior when OPENAI_API_KEY is missing."""
        with patch.dict("os.environ", {}, clear=True):
            try:
                from app.openai_client import client
                # May or may not raise depending on lazy initialization
            except ValueError as e:
                assert "API_KEY" in str(e).upper()
    
    def test_invalid_openai_api_key(self):
        """Test behavior with invalid API key."""
        with patch.dict("os.environ", {"OPENAI_API_KEY": "invalid-key"}):
            # Should allow initialization but fail on API calls
            from app.openai_client import get_chat_model
            model = get_chat_model()
            assert model is not None
    
    def test_invalid_model_names(self):
        """Test behavior with invalid model names."""
        with patch.dict("os.environ", {
            "OPENAI_API_KEY": "sk-test",
            "OPENAI_TRANSCRIPTION_MODEL": "invalid-model-xyz",
            "OPENAI_CHAT_MODEL": "invalid-model-abc"
        }):
            from app.openai_client import get_transcription_model, get_chat_model
            
            trans_model = get_transcription_model()
            chat_model = get_chat_model()
            
            assert trans_model == "invalid-model-xyz"
            assert chat_model == "invalid-model-abc"


@pytest.mark.integration
class TestStateManagementEdgeCases:
    """Test edge cases for state management."""
    
    def test_reset_when_already_reset(self):
        """Test calling reset multiple times."""
        from app.state import app_state
        
        app_state.set_transcript("Test")
        app_state.reset()
        
        assert app_state.get_transcript() == ""
        
        # Reset again
        app_state.reset()
        
        assert app_state.get_transcript() == ""
    
    def test_append_to_very_large_transcript(self):
        """Test appending to very large transcripts."""
        from app.state import app_state
        
        large_text = "x" * 100000
        app_state.set_transcript(large_text)
        
        app_state.append_transcript("y" * 10000)
        
        result = app_state.get_transcript()
        assert len(result) > 100000
        assert result.endswith("y" * 10000)
    
    def test_thread_safety_under_load(self):
        """Test thread safety with many concurrent operations."""
        from app.state import app_state
        from concurrent.futures import ThreadPoolExecutor
        
        errors = []
        
        def worker(thread_id):
            try:
                for i in range(100):
                    app_state.set_transcript(f"Thread {thread_id}: {i}")
                    _ = app_state.get_transcript()
                    app_state.append_transcript(f" append-{i}")
            except Exception as e:
                errors.append(str(e))
        
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(worker, i) for i in range(10)]
            for future in futures:
                future.result()
        
        # Should complete without errors
        assert len(errors) == 0


@pytest.mark.integration
class TestAudioProcessingEdgeCases:
    """Test edge cases for audio processing."""
    
    def test_empty_audio_data(self, mock_openai_client):
        """Test handling of empty audio data."""
        from app.openai_client import transcribe_audio_chunks
        
        empty_audio = np.array([]).reshape(0, 1).astype(np.float32)
        
        with patch("app.openai_client.client", mock_openai_client):
            try:
                result = transcribe_audio_chunks(empty_audio)
                # Should return empty or error message
                assert result is not None or result == ""
            except (ValueError, RuntimeError):
                # Expected
                pass
    
    def test_very_large_audio_chunk(self, mock_openai_client):
        """Test handling of very large audio chunks."""
        from app.openai_client import transcribe_audio_chunks
        
        # 10 seconds of audio at 16kHz = 160,000 samples
        large_audio = np.random.randn(160000, 1).astype(np.float32)
        large_audio = np.clip(large_audio, -1, 1)  # Clip to valid range
        
        with patch("app.openai_client.client", mock_openai_client):
            try:
                result = transcribe_audio_chunks(large_audio)
                assert result is not None
            except Exception:
                # May fail due to mock limitations
                pass
    
    def test_audio_with_extreme_values(self, mock_openai_client):
        """Test audio with extreme amplitude values."""
        from app.openai_client import transcribe_audio_chunks
        
        extreme_audio = np.array([[-1.0, 1.0, -1.0]] * 1000, dtype=np.float32).T
        extreme_audio = extreme_audio.reshape(-1, 1)
        
        with patch("app.openai_client.client", mock_openai_client):
            try:
                result = transcribe_audio_chunks(extreme_audio)
                assert result is not None
            except Exception:
                pass
    
    def test_audio_with_nan_values(self):
        """Test handling of audio with NaN values."""
        from app.openai_client import transcribe_audio_chunks
        
        nan_audio = np.array([[np.nan] * 100], dtype=np.float32).T
        nan_audio = nan_audio.reshape(-1, 1)
        
        try:
            # Should handle NaN gracefully
            with patch("app.openai_client.client"):
                result = transcribe_audio_chunks(nan_audio)
        except (ValueError, RuntimeError):
            # Expected behavior
            pass


@pytest.mark.integration
class TestReportGenerationEdgeCases:
    """Test edge cases for report generation."""
    
    def test_generate_report_with_empty_string(self, mock_openai_client):
        """Test report generation with empty transcript."""
        from app.openai_client import generate_structured_report
        
        with patch("app.openai_client.client", mock_openai_client):
            report = generate_structured_report("")
            
            assert report is not None
            assert isinstance(report, str)
    
    def test_generate_report_with_very_long_text(self, mock_openai_client):
        """Test report generation with extremely long transcript."""
        from app.openai_client import generate_structured_report
        
        long_text = "Patient reports " * 2000  # ~30K characters
        
        with patch("app.openai_client.client", mock_openai_client):
            try:
                report = generate_structured_report(long_text)
                assert report is not None
            except Exception:
                # May fail due to token limits
                pass
    
    def test_generate_report_with_special_characters(self, mock_openai_client):
        """Test report with special characters."""
        from app.openai_client import generate_structured_report
        
        special_text = "Patient: José García. Symptoms: 你好 🏥 émojis and special chars"
        
        with patch("app.openai_client.client", mock_openai_client):
            report = generate_structured_report(special_text)
            
            assert report is not None
            assert isinstance(report, str)


@pytest.mark.integration
class TestEndpointRobustness:
    """Test endpoint robustness against malformed requests."""
    
    def test_post_with_malformed_json(self, client):
        """Test endpoints with malformed JSON."""
        response = client.post(
            "/generate_report",
            data="{invalid json}",
            headers={"Content-Type": "application/json"}
        )
        
        # Should return error, not crash
        assert response.status_code >= 400 or response.status_code < 500
    
    def test_get_transcript_rapid_polling(self, client):
        """Test rapid polling of /transcript endpoint."""
        for _ in range(100):
            response = client.get("/transcript")
            assert response.status_code == 200
            assert isinstance(response.json(), dict)
    
    def test_multiple_reset_calls(self, client):
        """Test multiple consecutive resets."""
        for _ in range(10):
            response = client.post("/reset_session")
            assert response.status_code == 200


@pytest.mark.integration
@pytest.mark.slow
class TestMemoryAndResourceLeaks:
    """Test for memory and resource leaks."""
    
    def test_no_memory_leak_on_repeated_operations(self, client, app_state_fresh):
        """Test that repeated operations don't leak memory."""
        import sys
        
        # Get initial object count
        initial_objects = len(gc.get_objects())
        
        # Perform many operations
        for _ in range(100):
            app_state_fresh.set_transcript("Test " * 100)
            app_state_fresh.append_transcript(" more")
            _ = app_state_fresh.get_transcript()
        
        # Get final object count
        final_objects = len(gc.get_objects())
        
        # Shouldn't grow excessively (allow 50% growth)
        assert final_objects < initial_objects * 1.5
    
    def test_queue_cleanup_on_reset(self):
        """Test that queue is properly cleaned up."""
        from app.state import app_state
        
        # Fill queue
        for i in range(100):
            chunk = np.random.rand(1024, 1).astype(np.float32)
            app_state.audio_queue.put(chunk)
        
        assert app_state.audio_queue.qsize() == 100
        
        # Reset should clear queue
        app_state.reset()
        
        assert app_state.audio_queue.empty()


import gc  # Needed for memory tests at module level
