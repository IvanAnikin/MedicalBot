"""
MedicalBot Test Suite

This package contains comprehensive automated tests for the MedicalBot application.

Test Organization:
- test_state.py: Unit tests for app/state.py (thread-safe state management)
- test_audio_manager.py: Integration tests for app/audio_manager.py (audio recording)
- test_openai_client.py: Integration tests for app/openai_client.py (OpenAI API)
- test_endpoints.py: Integration tests for FastAPI endpoints
- test_edge_cases.py: Edge case and error scenario tests

Running Tests:
    pytest                          # Run all tests
    pytest -v                       # Verbose output
    pytest -m unit                  # Run only unit tests
    pytest -m integration           # Run only integration tests
    pytest -m slow                  # Run only slow tests
    pytest test_state.py            # Run specific test file
    pytest -k "test_start_recording" # Run tests matching pattern
    pytest --cov=app                # Run with coverage report
"""

__all__ = [
    "test_state",
    "test_audio_manager",
    "test_openai_client",
    "test_endpoints",
    "test_edge_cases",
]
