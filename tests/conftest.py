"""
Pytest configuration and shared fixtures for MedicalBot tests.
Provides mocks, fixtures, and test utilities.
"""

import pytest
import os
import sys
from unittest.mock import Mock, MagicMock, patch
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.state import AppState


@pytest.fixture
def app_state_fresh():
    """Provide a fresh AppState instance for each test."""
    state = AppState()
    yield state
    state.reset()


@pytest.fixture
def mock_env():
    """Provide mock environment variables."""
    with patch.dict(os.environ, {
        "OPENAI_API_KEY": "sk-test-key-12345",
        "OPENAI_TRANSCRIPTION_MODEL": "whisper-1",
        "OPENAI_CHAT_MODEL": "gpt-4o-mini",
        "APP_PORT": "8000"
    }):
        yield


@pytest.fixture
def mock_sounddevice():
    """Mock sounddevice module for audio tests."""
    with patch("app.audio_manager.sd") as mock_sd:
        # Mock the InputStream context manager
        mock_stream = MagicMock()
        mock_stream.__enter__ = Mock(return_value=mock_stream)
        mock_stream.__exit__ = Mock(return_value=None)
        
        # Mock read method to return audio data a finite number of times
        import numpy as np
        mock_audio_chunk = np.random.rand(1024, 1).astype(np.float32)
        call_count = {"n": 0}

        def read_side_effect(frames):
            # Return a limited number of chunks, then raise to stop the
            # recording thread in tests to avoid runaway loops that fill memory.
            call_count["n"] += 1
            if call_count["n"] <= 50:
                return (mock_audio_chunk, False)
            # After a short series of chunks, simulate end-of-stream
            raise IOError("Mock end of stream")

        mock_stream.read.side_effect = read_side_effect
        
        mock_sd.InputStream.return_value = mock_stream
        mock_sd.query_devices.return_value = [
            {'name': 'Built-in Microphone', 'max_input_channels': 1}
        ]
        
        yield mock_sd


@pytest.fixture
def mock_openai_client():
    """Mock OpenAI client for transcription and chat tests."""
    with patch("app.openai_client.client") as mock_client:
        # Mock transcription response
        mock_transcription = Mock()
        mock_transcription.text = "Patient reports fever and cough for 3 days"
        mock_client.audio.transcriptions.create.return_value = mock_transcription
        
        # Mock chat completion response
        mock_chat = Mock()
        mock_chat.choices = [Mock()]
        mock_chat.choices[0].message.content = """STRUCTURED MEDICAL REPORT

Patient Identification: Not mentioned in transcript

Chief Complaint / Reason for Visit: Patient reported fever and cough

History of Present Illness: Symptoms for 3 days

Past Medical History / Allergies / Medications: Not mentioned in transcript

Objective Findings: Not mentioned in transcript

Assessment: Upper respiratory infection

Plan: Rest, fluids, follow-up if symptoms worsen"""
        
        mock_client.chat.completions.create.return_value = mock_chat
        
        yield mock_client


@pytest.fixture
def mock_all_audio_and_api(mock_sounddevice, mock_openai_client, mock_env):
    """Convenience fixture that mocks all external dependencies."""
    yield mock_sounddevice, mock_openai_client


@pytest.fixture
def client():
    """Provide a FastAPI test client."""
    from fastapi.testclient import TestClient
    from main import app
    
    yield TestClient(app)


@pytest.fixture
def sample_audio_data():
    """Provide sample audio data for testing."""
    import numpy as np
    # 1 second of audio at 16kHz
    sample_rate = 16000
    duration = 1.0
    frequency = 440  # A4 note
    t = np.linspace(0, duration, int(sample_rate * duration))
    # Sine wave at 440 Hz
    audio = np.sin(2 * np.pi * frequency * t).astype(np.float32)
    # Add some realistic noise
    audio += np.random.normal(0, 0.01, len(audio))
    return audio.reshape(-1, 1)  # Make it (N, 1) shape for mono


@pytest.fixture
def sample_transcript():
    """Provide sample medical transcript for testing."""
    return """
    Patient is a 45-year-old male presenting with fever for 3 days.
    Temperature is 101.5 degrees Fahrenheit.
    He has a cough and sore throat.
    No prior surgeries.
    Allergic to Penicillin.
    Currently on no medications.
    Physical exam shows red throat, no lymphadenopathy.
    Lungs are clear to auscultation.
    Assessment: Viral pharyngitis.
    Plan: Rest, fluids, ibuprofen for pain, follow up in 1 week if symptoms persist.
    """


# Marker helpers
def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "unit: mark test as a unit test")
    config.addinivalue_line("markers", "integration: mark test as an integration test")
    config.addinivalue_line("markers", "slow: mark test as slow")
    config.addinivalue_line("markers", "api: mark test as requiring API calls")
    config.addinivalue_line("markers", "audio: mark test as audio-related")
    config.addinivalue_line("markers", "e2e: mark test as end-to-end")
