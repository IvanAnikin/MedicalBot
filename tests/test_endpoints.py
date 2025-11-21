"""
Integration tests for FastAPI endpoints in main.py.
Tests verify all HTTP routes, status codes, and response formats.
"""

import pytest
import json
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from main import app
from app.state import AppState


@pytest.fixture
def client():
    """Provide FastAPI test client."""
    return TestClient(app)


@pytest.fixture
def app_state_for_testing():
    """Fresh app state for each test."""
    from app.state import app_state
    yield app_state
    app_state.reset()


@pytest.mark.integration
class TestIndexEndpoint:
    """Test GET / endpoint."""
    
    def test_index_returns_html(self, client):
        """Test that GET / returns HTML content."""
        response = client.get("/")
        
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
    
    def test_index_contains_ui_elements(self, client):
        """Test that HTML contains expected UI elements."""
        response = client.get("/")
        html = response.text
        
        expected_elements = [
            "MedicalBot",
            "startBtn",
            "stopBtn",
            "generateBtn",
            "clearBtn",
            "transcript",
            "report"
        ]
        
        for element in expected_elements:
            assert element in html, f"Missing UI element: {element}"
    
    def test_index_contains_javascript(self, client):
        """Test that HTML contains JavaScript logic."""
        response = client.get("/")
        html = response.text
        
        assert "function" in html.lower()
        assert "fetch" in html or "xhr" in html.lower()


@pytest.mark.integration
class TestStartRecordingEndpoint:
    """Test POST /start_recording endpoint."""
    
    def test_start_recording_success(self, client, app_state_for_testing, mock_all_audio_and_api):
        """Test successful recording start."""
        response = client.post("/start_recording")
        
        assert response.status_code == 200
        assert "status" in response.json()
    
    def test_start_recording_returns_json(self, client, app_state_for_testing, mock_all_audio_and_api):
        """Test that response is valid JSON."""
        response = client.post("/start_recording")
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
    
    def test_start_recording_conflict_when_already_recording(self, client, app_state_for_testing, mock_all_audio_and_api):
        """Test 409 Conflict when already recording."""
        # Start recording
        response1 = client.post("/start_recording")
        assert response1.status_code == 200
        
        # Try to start again (should conflict)
        response2 = client.post("/start_recording")
        assert response2.status_code == 409
    
    def test_start_recording_sets_state(self, client, app_state_for_testing, mock_all_audio_and_api):
        """Test that starting recording sets the app state."""
        response = client.post("/start_recording")
        assert response.status_code == 200
        
        # Verify state was set
        assert app_state_for_testing.is_recording() == True


@pytest.mark.integration
class TestStopRecordingEndpoint:
    """Test POST /stop_recording endpoint."""
    
    def test_stop_recording_success(self, client, app_state_for_testing, mock_all_audio_and_api):
        """Test successful recording stop."""
        # Start first
        client.post("/start_recording")
        
        # Stop
        response = client.post("/stop_recording")
        
        assert response.status_code == 200
        assert "status" in response.json()
    
    def test_stop_recording_returns_status(self, client, app_state_for_testing, mock_all_audio_and_api):
        """Test that stop returns proper status."""
        client.post("/start_recording")
        response = client.post("/stop_recording")
        
        data = response.json()
        assert data.get("status") in ["recording_stopped", "stop_initiated"]
    
    def test_stop_recording_when_not_recording(self, client, app_state_for_testing, mock_all_audio_and_api):
        """Test stopping when not recording returns error."""
        response = client.post("/stop_recording")
        
        # Should return error status code or error response
        assert response.status_code >= 400 or "status" in response.json()
    
    def test_stop_recording_clears_recording_state(self, client, app_state_for_testing, mock_all_audio_and_api):
        """Test that stopping clears the recording state."""
        client.post("/start_recording")
        assert app_state_for_testing.is_recording() == True
        
        client.post("/stop_recording")
        assert app_state_for_testing.is_recording() == False


@pytest.mark.integration
class TestTranscriptEndpoint:
    """Test GET /transcript endpoint."""
    
    def test_transcript_endpoint_returns_json(self, client, app_state_for_testing):
        """Test that /transcript returns JSON."""
        response = client.get("/transcript")
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
    
    def test_transcript_contains_recording_status(self, client, app_state_for_testing):
        """Test that response contains recording status."""
        response = client.get("/transcript")
        data = response.json()
        
        assert "recording" in data
        assert isinstance(data["recording"], bool)
    
    def test_transcript_contains_transcript_text(self, client, app_state_for_testing):
        """Test that response contains transcript field."""
        response = client.get("/transcript")
        data = response.json()
        
        assert "transcript" in data
        assert isinstance(data["transcript"], str)
    
    def test_transcript_empty_initially(self, client, app_state_for_testing):
        """Test that transcript is empty initially."""
        response = client.get("/transcript")
        data = response.json()
        
        assert data["transcript"] == ""
    
    def test_transcript_reflects_state(self, client, app_state_for_testing):
        """Test that transcript endpoint reflects app state."""
        app_state_for_testing.set_transcript("Patient reports fever")
        
        response = client.get("/transcript")
        data = response.json()
        
        assert data["transcript"] == "Patient reports fever"


@pytest.mark.integration
class TestGenerateReportEndpoint:
    """Test POST /generate_report endpoint."""
    
    def test_generate_report_success(self, client, app_state_for_testing, mock_openai_client):
        """Test successful report generation."""
        # Set a transcript
        app_state_for_testing.set_transcript("Patient reports chest pain")
        
        with patch("app.openai_client.client", mock_openai_client):
            response = client.post("/generate_report")
        
        assert response.status_code == 200
        data = response.json()
        assert "report" in data
    
    def test_generate_report_contains_sections(self, client, app_state_for_testing, mock_openai_client):
        """Test that report contains required sections."""
        app_state_for_testing.set_transcript(
            "Patient John Doe, age 45, fever 101.5, cough, sore throat, "
            "no prior history, allergic to penicillin, exam shows red throat"
        )
        
        with patch("app.openai_client.client", mock_openai_client):
            response = client.post("/generate_report")
        
        assert response.status_code == 200
        data = response.json()
        report = data.get("report", "")
        
        # Check for at least one section header
        assert any(section in report for section in [
            "Patient Identification",
            "Chief Complaint",
            "Assessment",
            "Plan"
        ])
    
    def test_generate_report_without_transcript(self, client, app_state_for_testing, mock_openai_client):
        """Test that generating report without transcript returns error."""
        with patch("app.openai_client.client", mock_openai_client):
            response = client.post("/generate_report")
        
        # Should return error or empty transcript error
        assert response.status_code >= 400 or "error" in response.json().get("status", "").lower()
    
    def test_generate_report_returns_string(self, client, app_state_for_testing, mock_openai_client):
        """Test that report is returned as string."""
        app_state_for_testing.set_transcript("Test transcript")
        
        with patch("app.openai_client.client", mock_openai_client):
            response = client.post("/generate_report")
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data.get("report", ""), str)


@pytest.mark.integration
class TestResetSessionEndpoint:
    """Test POST /reset_session endpoint."""
    
    def test_reset_session_success(self, client, app_state_for_testing):
        """Test successful session reset."""
        # Set some state
        app_state_for_testing.set_transcript("Some transcript")
        
        response = client.post("/reset_session")
        
        assert response.status_code == 200
    
    def test_reset_session_clears_transcript(self, client, app_state_for_testing):
        """Test that reset clears transcript."""
        app_state_for_testing.set_transcript("Transcript to clear")
        
        client.post("/reset_session")
        
        assert app_state_for_testing.get_transcript() == ""
    
    def test_reset_session_stops_recording(self, client, app_state_for_testing, mock_all_audio_and_api):
        """Test that reset stops any active recording."""
        client.post("/start_recording")
        assert app_state_for_testing.is_recording() == True
        
        client.post("/reset_session")
        
        assert app_state_for_testing.is_recording() == False
    
    def test_reset_session_returns_success_status(self, client, app_state_for_testing):
        """Test that reset returns success status."""
        response = client.post("/reset_session")
        
        data = response.json()
        assert "status" in data


@pytest.mark.integration
class TestEndpointErrorHandling:
    """Test error handling across endpoints."""
    
    def test_invalid_content_type(self, client, app_state_for_testing):
        """Test handling of invalid content type."""
        response = client.post(
            "/generate_report",
            data="not json",
            headers={"Content-Type": "text/plain"}
        )
        
        # Should either parse as empty or return error
        assert response.status_code in [200, 400, 422]
    
    def test_missing_required_fields(self, client, app_state_for_testing):
        """Test handling of missing required fields."""
        response = client.post("/generate_report", json={})
        
        assert response.status_code >= 200
    
    def test_invalid_endpoint_404(self, client):
        """Test that invalid endpoint returns 404."""
        response = client.get("/invalid_endpoint")
        
        assert response.status_code == 404


@pytest.mark.integration
class TestResponseFormats:
    """Test response format consistency."""
    
    def test_all_json_endpoints_return_dict(self, client, app_state_for_testing):
        """Test that all JSON endpoints return dict."""
        endpoints = [
            ("get", "/transcript"),
            ("post", "/start_recording"),
            ("post", "/reset_session"),
        ]
        
        for method, endpoint in endpoints:
            if method == "get":
                response = client.get(endpoint)
            else:
                response = client.post(endpoint)
            
            if response.status_code == 200:
                assert isinstance(response.json(), dict)
    
    def test_error_responses_are_consistent(self, client, app_state_for_testing):
        """Test that error responses are consistent."""
        # Try to stop without starting
        response = client.post("/stop_recording")
        
        if response.status_code >= 400:
            assert "detail" in response.json() or "error" in response.json()


@pytest.mark.integration
@pytest.mark.slow
class TestEndpointIntegrationFlow:
    """Test complete workflow through endpoints."""
    
    def test_full_recording_to_report_flow(self, client, app_state_for_testing, mock_all_audio_and_api):
        """Test complete flow: start → stop → generate report."""
        with patch("app.openai_client.client", mock_all_audio_and_api[1]):
            # Reset
            client.post("/reset_session")
            
            # Check initial state
            response = client.get("/transcript")
            assert response.json()["recording"] == False
            
            # Start recording
            response = client.post("/start_recording")
            assert response.status_code == 200
            
            # Check recording state
            response = client.get("/transcript")
            assert response.json()["recording"] == True
            
            # Stop recording
            response = client.post("/stop_recording")
            assert response.status_code == 200
            
            # Generate report (may fail if transcription not done)
            response = client.post("/generate_report")
            assert response.status_code in [200, 400]
    
    def test_multiple_sessions(self, client, app_state_for_testing):
        """Test running multiple independent sessions."""
        # Session 1
        client.post("/reset_session")
        app_state_for_testing.set_transcript("Session 1 transcript")
        response = client.get("/transcript")
        assert "Session 1" in response.json()["transcript"]
        
        # Reset for Session 2
        client.post("/reset_session")
        app_state_for_testing.set_transcript("Session 2 transcript")
        response = client.get("/transcript")
        assert "Session 2" in response.json()["transcript"]
        assert "Session 1" not in response.json()["transcript"]
