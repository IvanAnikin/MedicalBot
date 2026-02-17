"""
Comprehensive end-to-end tests for the real-time voice-to-report feature.

Tests cover the complete pipeline:
  Start Recording → Audio Capture → Transcription → Auto-Report Generation → Polling → Stop

Validates:
  - /report endpoint behaviour
  - Auto-report generation triggered by transcription worker
  - /stop_recording returning auto-generated report
  - /reset_session clearing report state
  - Polling simulation (multiple GET /report calls)
  - Error / edge-case scenarios during auto-report generation
  - Thread-safety of report state under concurrent polling
  - Full HTTP-level round-trips via FastAPI TestClient
"""

import gc
import time
import threading
import numpy as np
import pytest
from concurrent.futures import ThreadPoolExecutor, as_completed
from unittest.mock import patch, Mock, MagicMock

from fastapi.testclient import TestClient

from main import app
from app.state import AppState, app_state


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_global_state():
    """Ensure global app_state is clean before and after every test."""
    app_state.reset()
    yield
    # Defensive cleanup – stop lingering threads if any
    app_state.stop_event.set()
    if app_state.recording_thread and app_state.recording_thread.is_alive():
        app_state.recording_thread.join(timeout=3)
    if app_state.transcription_thread and app_state.transcription_thread.is_alive():
        app_state.transcription_thread.join(timeout=3)
    app_state.reset()


@pytest.fixture
def client():
    """FastAPI test client."""
    return TestClient(app)


@pytest.fixture
def mock_openai():
    """Mock the OpenAI client with realistic transcription and report responses."""
    with patch("app.openai_client.client") as mock_client:
        # -- Transcription mock --
        mock_transcription = Mock()
        mock_transcription.text = (
            "Patient is a 62-year-old male presenting with chest pain radiating to the left arm. "
            "Pain started two hours ago at rest. History of hypertension and type 2 diabetes. "
            "Currently on metformin 500 mg twice daily and lisinopril 10 mg daily. "
            "Allergic to sulfa drugs. Vitals: BP 158/92, HR 96, Temp 98.6 F. "
            "EKG shows ST depression in leads V4-V6. "
            "Assessment: Unstable angina, rule out NSTEMI. "
            "Plan: Admit to cardiac care unit, serial troponins, heparin drip, cardiology consult."
        )
        mock_client.audio.transcriptions.create.return_value = mock_transcription

        # -- Chat / report mock --
        report_text = (
            "STRUCTURED MEDICAL REPORT\n\n"
            "**Patient Identification**\n"
            "- 62-year-old male\n\n"
            "**Chief Complaint / Reason for Visit**\n"
            "- Chest pain radiating to left arm\n\n"
            "**History of Present Illness (HPI)**\n"
            "- Pain started 2 hours ago at rest\n\n"
            "**Past Medical History / Allergies / Medications**\n"
            "- History: Hypertension, Type 2 Diabetes\n"
            "- Allergies: Sulfa drugs\n"
            "- Medications: Metformin 500 mg BID, Lisinopril 10 mg daily\n\n"
            "**Objective Findings**\n"
            "- BP 158/92, HR 96, Temp 98.6 F\n"
            "- EKG: ST depression V4-V6\n\n"
            "**Assessment**\n"
            "- Unstable angina, rule out NSTEMI\n\n"
            "**Plan**\n"
            "- Admit to cardiac care unit\n"
            "- Serial troponins\n"
            "- Heparin drip\n"
            "- Cardiology consult"
        )
        mock_chat = Mock()
        mock_chat.choices = [Mock()]
        mock_chat.choices[0].message.content = report_text
        mock_client.chat.completions.create.return_value = mock_chat

        yield mock_client


@pytest.fixture
def mock_sounddevice():
    """Mock sounddevice to avoid real hardware dependency."""
    with patch("app.audio_manager.sd") as mock_sd:
        mock_stream = MagicMock()
        mock_stream.__enter__ = Mock(return_value=mock_stream)
        mock_stream.__exit__ = Mock(return_value=None)

        audio_chunk = np.random.rand(1024, 1).astype(np.float32) * 0.1
        call_count = {"n": 0}

        def read_side_effect(frames):
            call_count["n"] += 1
            if call_count["n"] <= 50:
                return (audio_chunk, False)
            raise IOError("Mock end of stream")

        mock_stream.read.side_effect = read_side_effect
        mock_sd.InputStream.return_value = mock_stream
        yield mock_sd


@pytest.fixture
def mock_env():
    """Provide mandatory environment variables."""
    with patch.dict("os.environ", {
        "OPENAI_API_KEY": "sk-test-key-for-e2e",
        "OPENAI_TRANSCRIPTION_MODEL": "whisper-1",
        "OPENAI_CHAT_MODEL": "gpt-4o-mini",
    }):
        yield


@pytest.fixture
def full_mocks(mock_sounddevice, mock_openai, mock_env):
    """Convenience bundle of all external mocks."""
    yield mock_sounddevice, mock_openai


# ===========================================================================
# 1. /report endpoint tests
# ===========================================================================

@pytest.mark.integration
class TestReportEndpoint:
    """Tests for the GET /report endpoint."""

    def test_report_endpoint_returns_200(self, client):
        """GET /report should return 200."""
        resp = client.get("/report")
        assert resp.status_code == 200

    def test_report_endpoint_json_schema(self, client):
        """Response must contain 'recording', 'report', and 'transcript' keys."""
        data = client.get("/report").json()
        assert "recording" in data
        assert "report" in data
        assert "transcript" in data

    def test_report_endpoint_types(self, client):
        """Verify field types."""
        data = client.get("/report").json()
        assert isinstance(data["recording"], bool)
        assert isinstance(data["report"], str)
        assert isinstance(data["transcript"], str)

    def test_report_endpoint_initially_empty(self, client):
        """Report and transcript should be empty at startup."""
        data = client.get("/report").json()
        assert data["recording"] is False
        assert data["report"] == ""
        assert data["transcript"] == ""

    def test_report_endpoint_reflects_manual_state(self, client):
        """If we manually set report on the state, /report should reflect it."""
        app_state.set_report("Manual report content")
        app_state.set_transcript("Manual transcript")

        data = client.get("/report").json()
        assert data["report"] == "Manual report content"
        assert data["transcript"] == "Manual transcript"

    def test_report_endpoint_recording_flag_true(self, client):
        """When recording is active, 'recording' should be True."""
        app_state.set_recording_active(True)
        data = client.get("/report").json()
        assert data["recording"] is True

    def test_report_endpoint_recording_flag_false(self, client):
        """When recording is inactive, 'recording' should be False."""
        app_state.set_recording_active(False)
        data = client.get("/report").json()
        assert data["recording"] is False


# ===========================================================================
# 2. Auto-report generation (transcription worker → report)
# ===========================================================================

@pytest.mark.integration
class TestAutoReportGeneration:
    """Verify that stopping recording triggers automatic report generation."""

    def test_auto_report_generated_on_stop(self, client, full_mocks):
        """Full HTTP round-trip: start → stop → report should be non-empty."""
        resp = client.post("/start_recording")
        assert resp.status_code == 200

        # Give threads a moment to capture audio
        time.sleep(0.5)

        resp = client.post("/stop_recording")
        assert resp.status_code == 200
        data = resp.json()

        # The auto-generated report should be present in the stop response
        assert data.get("status") == "recording_stopped"
        assert len(data.get("report", "")) > 0, "Report should be auto-generated on stop"
        assert len(data.get("transcript", "")) > 0, "Transcript should be available on stop"

    def test_auto_report_contains_medical_sections(self, client, full_mocks):
        """Auto-generated report must include key medical sections."""
        client.post("/start_recording")
        time.sleep(0.5)
        data = client.post("/stop_recording").json()

        report = data.get("report", "")
        expected_sections = [
            "Patient Identification",
            "Chief Complaint",
            "History of Present Illness",
            "Assessment",
            "Plan",
        ]
        for section in expected_sections:
            assert section in report, f"Auto-generated report missing section: {section}"

    def test_auto_report_available_via_report_endpoint(self, client, full_mocks):
        """After stop, GET /report should serve the same auto-generated report."""
        client.post("/start_recording")
        time.sleep(0.5)
        stop_data = client.post("/stop_recording").json()

        poll_data = client.get("/report").json()
        assert poll_data["report"] == stop_data["report"]
        assert poll_data["recording"] is False

    def test_transcript_also_stored(self, client, full_mocks):
        """Transcript should be stored alongside the report."""
        client.post("/start_recording")
        time.sleep(0.5)
        client.post("/stop_recording")

        data = client.get("/report").json()
        assert len(data["transcript"]) > 0
        assert "chest pain" in data["transcript"].lower()

    def test_auto_report_preserves_clinical_details(self, client, full_mocks):
        """Report should preserve key clinical info from the transcript."""
        client.post("/start_recording")
        time.sleep(0.5)
        data = client.post("/stop_recording").json()

        report = data.get("report", "").lower()
        clinical_terms = ["chest pain", "hypertension", "metformin", "angina", "troponin"]
        found = [t for t in clinical_terms if t in report]
        assert len(found) >= 3, f"Report should contain clinical terms, found only: {found}"


# ===========================================================================
# 3. Stop recording response validation
# ===========================================================================

@pytest.mark.integration
class TestStopRecordingReportResponse:
    """Validate the /stop_recording response now includes report data."""

    def test_stop_response_schema(self, client, full_mocks):
        """Stop response must include status, transcript, and report."""
        client.post("/start_recording")
        time.sleep(0.3)
        data = client.post("/stop_recording").json()

        assert "status" in data
        assert "transcript" in data
        assert "report" in data

    def test_stop_when_not_recording_returns_empty_report(self, client):
        """Stopping without an active recording should return empty report."""
        data = client.post("/stop_recording").json()
        assert data.get("report", "") == ""
        assert data.get("transcript", "") == ""

    def test_stop_clears_recording_flag(self, client, full_mocks):
        """After stop, recording should be False."""
        client.post("/start_recording")
        time.sleep(0.3)
        client.post("/stop_recording")

        assert app_state.is_recording() is False


# ===========================================================================
# 4. Reset / Clear session clears report
# ===========================================================================

@pytest.mark.integration
class TestResetClearsReport:
    """Verify that resetting session clears the report."""

    def test_reset_clears_report(self, client, full_mocks):
        """POST /reset_session should clear the report."""
        client.post("/start_recording")
        time.sleep(0.5)
        client.post("/stop_recording")

        # Confirm report was generated
        data = client.get("/report").json()
        assert len(data["report"]) > 0

        # Now reset
        resp = client.post("/reset_session")
        assert resp.status_code == 200

        data = client.get("/report").json()
        assert data["report"] == ""
        assert data["transcript"] == ""

    def test_reset_clears_report_without_recording(self, client):
        """Reset should work even if no recording happened."""
        app_state.set_report("Some leftover report")
        app_state.set_transcript("Some leftover transcript")

        client.post("/reset_session")

        data = client.get("/report").json()
        assert data["report"] == ""
        assert data["transcript"] == ""

    def test_can_record_again_after_reset(self, client, full_mocks):
        """After reset, a new recording session should work end-to-end."""
        # First session
        client.post("/start_recording")
        time.sleep(0.3)
        client.post("/stop_recording")

        first_report = client.get("/report").json()["report"]
        assert len(first_report) > 0

        # Reset
        client.post("/reset_session")

        # Second session
        client.post("/start_recording")
        time.sleep(0.3)
        data = client.post("/stop_recording").json()

        assert len(data["report"]) > 0


# ===========================================================================
# 5. Polling simulation
# ===========================================================================

@pytest.mark.integration
class TestPollingSimulation:
    """Simulate frontend polling behaviour."""

    def test_polling_during_recording_returns_empty_report(self, client, full_mocks):
        """While recording is in progress report should still be empty
        (report is generated only after transcription completes)."""
        client.post("/start_recording")

        # Poll immediately while still recording
        data = client.get("/report").json()
        assert data["recording"] is True
        # Report is empty because transcription hasn't finished yet
        assert data["report"] == ""

        # Cleanup
        client.post("/stop_recording")

    def test_polling_after_stop_returns_report(self, client, full_mocks):
        """After stopping, the polled report should be populated."""
        client.post("/start_recording")
        time.sleep(0.3)
        client.post("/stop_recording")

        data = client.get("/report").json()
        assert data["recording"] is False
        assert len(data["report"]) > 0

    def test_rapid_polling_stability(self, client, full_mocks):
        """Rapid polling (100 requests) should not cause errors."""
        client.post("/start_recording")
        time.sleep(0.2)

        for _ in range(100):
            resp = client.get("/report")
            assert resp.status_code == 200
            data = resp.json()
            assert isinstance(data["recording"], bool)
            assert isinstance(data["report"], str)

        client.post("/stop_recording")

    def test_polling_shows_report_transition(self, client, full_mocks):
        """Demonstrate the empty→populated transition as seen by a polling client."""
        client.post("/start_recording")

        # During recording: report empty
        pre_data = client.get("/report").json()
        assert pre_data["report"] == ""

        time.sleep(0.3)
        client.post("/stop_recording")

        # After stop: report populated
        post_data = client.get("/report").json()
        assert len(post_data["report"]) > 0

    def test_concurrent_polling(self, client, full_mocks):
        """Multiple threads polling /report should all get consistent data."""
        client.post("/start_recording")
        time.sleep(0.3)
        client.post("/stop_recording")

        results = []

        def poll():
            data = client.get("/report").json()
            results.append(data)

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(poll) for _ in range(20)]
            for f in as_completed(futures):
                f.result()

        # All responses should contain the same report
        reports = {r["report"] for r in results}
        assert len(reports) == 1, "All concurrent polls should return the same report"
        assert len(reports.pop()) > 0


# ===========================================================================
# 6. Error scenarios during auto-report generation
# ===========================================================================

@pytest.mark.integration
class TestAutoReportErrorHandling:
    """Test behaviour when auto-report generation fails."""

    def test_report_empty_when_generation_fails(self, client, mock_sounddevice, mock_env):
        """If GPT report generation throws, report should be empty but no crash."""
        with patch("app.openai_client.client") as mock_client:
            # Transcription succeeds
            mock_t = Mock()
            mock_t.text = "Patient has a headache"
            mock_client.audio.transcriptions.create.return_value = mock_t

            # Report generation fails
            mock_client.chat.completions.create.side_effect = Exception("GPT quota exceeded")

            resp = client.post("/start_recording")
            assert resp.status_code == 200
            time.sleep(0.5)

            resp = client.post("/stop_recording")
            assert resp.status_code == 200
            data = resp.json()

            # Report should be empty (error handled gracefully)
            assert data.get("report", "") == ""
            # But transcript should still be set
            assert len(data.get("transcript", "")) > 0

    def test_transcript_empty_when_transcription_fails(self, client, mock_sounddevice, mock_env):
        """If Whisper transcription throws, both transcript and report should be empty."""
        with patch("app.openai_client.client") as mock_client:
            mock_client.audio.transcriptions.create.side_effect = Exception("Whisper unavailable")
            mock_client.chat.completions.create.return_value = Mock()

            client.post("/start_recording")
            time.sleep(0.5)
            data = client.post("/stop_recording").json()

            # Both should be empty since transcription failed
            assert data.get("transcript", "") == ""
            assert data.get("report", "") == ""

    def test_report_empty_string_not_none_on_error(self, client, mock_sounddevice, mock_env):
        """On error, the report field should be '' (empty string), never None."""
        with patch("app.openai_client.client") as mock_client:
            mock_t = Mock()
            mock_t.text = "Test transcript"
            mock_client.audio.transcriptions.create.return_value = mock_t
            mock_client.chat.completions.create.side_effect = RuntimeError("model down")

            client.post("/start_recording")
            time.sleep(0.5)
            data = client.post("/stop_recording").json()

            assert data["report"] is not None
            assert isinstance(data["report"], str)

    def test_server_stable_after_report_error(self, client, mock_sounddevice, mock_env):
        """Server should remain operational after a report generation error."""
        with patch("app.openai_client.client") as mock_client:
            mock_t = Mock()
            mock_t.text = "Test"
            mock_client.audio.transcriptions.create.return_value = mock_t
            mock_client.chat.completions.create.side_effect = Exception("fail")

            client.post("/start_recording")
            time.sleep(0.3)
            client.post("/stop_recording")

        # After error, endpoints should still work
        resp = client.get("/report")
        assert resp.status_code == 200

        resp = client.get("/transcript")
        assert resp.status_code == 200

        resp = client.post("/reset_session")
        assert resp.status_code == 200


# ===========================================================================
# 7. State-level report management
# ===========================================================================

@pytest.mark.unit
class TestReportStateManagement:
    """Verify AppState report field thread-safety and correctness."""

    def test_set_and_get_report(self):
        state = AppState()
        state.set_report("Test report")
        assert state.get_report() == "Test report"

    def test_report_initially_empty(self):
        state = AppState()
        assert state.get_report() == ""

    def test_reset_clears_report(self):
        state = AppState()
        state.set_report("some report")
        state.reset()
        assert state.get_report() == ""

    def test_report_overwrite(self):
        state = AppState()
        state.set_report("first")
        state.set_report("second")
        assert state.get_report() == "second"

    def test_report_with_multiline_content(self):
        state = AppState()
        multiline = "Line 1\nLine 2\n\n**Bold**\n- bullet"
        state.set_report(multiline)
        assert state.get_report() == multiline

    def test_report_with_unicode(self):
        state = AppState()
        unicode_report = "Diagnóza: Akutní bronchitida 🏥\nPlán: Odpočinek"
        state.set_report(unicode_report)
        assert state.get_report() == unicode_report

    def test_concurrent_report_writes(self):
        """Multiple threads writing to report should not corrupt data."""
        state = AppState()
        errors = []

        def writer(report_text, iterations=200):
            try:
                for _ in range(iterations):
                    state.set_report(report_text)
                    read = state.get_report()
                    # Due to concurrency the read may be from another writer,
                    # but it should always be a complete string, never partial.
                    if not isinstance(read, str):
                        errors.append(f"Non-string report: {type(read)}")
            except Exception as e:
                errors.append(str(e))

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [
                executor.submit(writer, f"Report from thread {i}")
                for i in range(5)
            ]
            for f in as_completed(futures):
                f.result()

        assert len(errors) == 0, f"Thread safety errors: {errors}"

    def test_concurrent_read_while_writing(self):
        """Readers should never see partial writes."""
        state = AppState()
        long_report = "A" * 10_000
        errors = []

        def writer():
            for _ in range(100):
                state.set_report(long_report)
                state.set_report("")

        def reader():
            for _ in range(100):
                r = state.get_report()
                if r != "" and r != long_report:
                    errors.append(f"Partial read detected: len={len(r)}")

        threads = [
            threading.Thread(target=writer),
            threading.Thread(target=reader),
            threading.Thread(target=reader),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert len(errors) == 0, f"Partial reads detected: {errors}"


# ===========================================================================
# 8. Full end-to-end workflow tests
# ===========================================================================

@pytest.mark.integration
@pytest.mark.e2e
class TestFullWorkflowE2E:
    """Complete end-to-end workflow tests through the HTTP API."""

    def test_complete_single_session(self, client, full_mocks):
        """Single session: start → record → stop → verify report."""
        # Step 1: Verify clean state
        data = client.get("/report").json()
        assert data["recording"] is False
        assert data["report"] == ""

        # Step 2: Start recording
        resp = client.post("/start_recording")
        assert resp.status_code == 200
        assert resp.json()["status"] == "recording_started"

        # Step 3: Verify recording state
        data = client.get("/report").json()
        assert data["recording"] is True

        # Step 4: Let audio accumulate
        time.sleep(0.5)

        # Step 5: Stop recording
        resp = client.post("/stop_recording")
        assert resp.status_code == 200
        stop_data = resp.json()
        assert stop_data["status"] == "recording_stopped"

        # Step 6: Verify report was auto-generated
        assert len(stop_data["report"]) > 100
        assert len(stop_data["transcript"]) > 10

        # Step 7: Verify polling returns same data
        poll = client.get("/report").json()
        assert poll["report"] == stop_data["report"]
        assert poll["recording"] is False

    def test_multiple_sequential_sessions(self, client, full_mocks):
        """Run two full sessions back-to-back to verify state isolation."""
        for session_num in range(2):
            # Reset between sessions
            client.post("/reset_session")

            # Verify clean
            data = client.get("/report").json()
            assert data["report"] == "", f"Session {session_num}: report not clean after reset"

            # Run session
            client.post("/start_recording")
            time.sleep(0.3)
            stop_data = client.post("/stop_recording").json()

            assert len(stop_data["report"]) > 0, f"Session {session_num}: report not generated"

    def test_start_stop_start_without_reset(self, client, full_mocks):
        """Start→stop→start again to verify state transitions without explicit reset."""
        # First session
        client.post("/start_recording")
        time.sleep(0.3)
        first_stop = client.post("/stop_recording").json()
        first_report = first_stop["report"]
        assert len(first_report) > 0

        # Second session (start_recording resets state internally)
        resp = client.post("/start_recording")
        assert resp.status_code == 200

        time.sleep(0.3)
        second_stop = client.post("/stop_recording").json()
        assert len(second_stop["report"]) > 0

    def test_workflow_with_clear_all(self, client, full_mocks):
        """Simulate: record → stop → view report → clear all → verify empty."""
        client.post("/start_recording")
        time.sleep(0.3)
        client.post("/stop_recording")

        # Report should exist
        data = client.get("/report").json()
        assert len(data["report"]) > 0

        # Clear all (simulates "Clear All" button in UI)
        resp = client.post("/reset_session")
        assert resp.status_code == 200

        # Everything should be empty
        data = client.get("/report").json()
        assert data["report"] == ""
        assert data["transcript"] == ""
        assert data["recording"] is False

    def test_immediate_stop_after_start(self, client, full_mocks):
        """Start and immediately stop — should handle gracefully."""
        client.post("/start_recording")
        data = client.post("/stop_recording").json()

        # May or may not have transcript/report depending on timing,
        # but should not crash
        assert data["status"] == "recording_stopped"
        assert isinstance(data["report"], str)
        assert isinstance(data["transcript"], str)

    def test_double_stop_idempotent(self, client, full_mocks):
        """Stopping twice should not crash."""
        client.post("/start_recording")
        time.sleep(0.3)

        resp1 = client.post("/stop_recording")
        assert resp1.status_code == 200

        resp2 = client.post("/stop_recording")
        assert resp2.status_code == 200
        assert resp2.json().get("status") == "not_recording"

    def test_report_endpoint_serves_latest_report(self, client, full_mocks):
        """After generating a report, /report always returns the latest one."""
        client.post("/start_recording")
        time.sleep(0.3)
        client.post("/stop_recording")

        report1 = client.get("/report").json()["report"]
        report2 = client.get("/report").json()["report"]
        report3 = client.get("/report").json()["report"]

        # All should be identical and non-empty
        assert report1 == report2 == report3
        assert len(report1) > 0


# ===========================================================================
# 9. Interaction between /report and /transcript endpoints
# ===========================================================================

@pytest.mark.integration
class TestReportTranscriptConsistency:
    """Verify consistency between /report and /transcript endpoints."""

    def test_transcript_matches_between_endpoints(self, client, full_mocks):
        """/report and /transcript should return the same transcript."""
        client.post("/start_recording")
        time.sleep(0.3)
        client.post("/stop_recording")

        report_data = client.get("/report").json()
        transcript_data = client.get("/transcript").json()

        assert report_data["transcript"] == transcript_data["transcript"]

    def test_recording_flag_matches_between_endpoints(self, client, full_mocks):
        """Recording flag should be consistent across endpoints."""
        # Before recording
        assert client.get("/report").json()["recording"] is False
        assert client.get("/transcript").json()["recording"] is False

        # During recording
        client.post("/start_recording")
        assert client.get("/report").json()["recording"] is True
        assert client.get("/transcript").json()["recording"] is True

        # After recording
        time.sleep(0.3)
        client.post("/stop_recording")
        assert client.get("/report").json()["recording"] is False
        assert client.get("/transcript").json()["recording"] is False

    def test_generate_report_endpoint_still_works(self, client, full_mocks):
        """The legacy /generate_report endpoint should still function."""
        _, mock_openai = full_mocks
        app_state.set_transcript("Patient has a headache and fever")

        with patch("app.openai_client.client", mock_openai):
            resp = client.post("/generate_report")

        assert resp.status_code == 200
        assert "report" in resp.json()
        assert len(resp.json()["report"]) > 0


# ===========================================================================
# 10. Edge cases specific to real-time flow
# ===========================================================================

@pytest.mark.integration
class TestRealtimeEdgeCases:
    """Edge cases specific to the real-time feature."""

    def test_conflict_on_double_start(self, client, full_mocks):
        """Starting recording twice should return 409."""
        resp1 = client.post("/start_recording")
        assert resp1.status_code == 200

        resp2 = client.post("/start_recording")
        assert resp2.status_code == 409

        # Cleanup
        client.post("/stop_recording")

    def test_report_not_leaked_between_sessions(self, client, full_mocks):
        """Report from session 1 should not appear in session 2 after reset."""
        # Session 1
        client.post("/start_recording")
        time.sleep(0.3)
        s1 = client.post("/stop_recording").json()
        s1_report = s1["report"]
        assert len(s1_report) > 0

        # Reset
        client.post("/reset_session")

        # Before session 2 starts, report should be empty
        data = client.get("/report").json()
        assert data["report"] == ""

    def test_very_fast_start_stop_cycle(self, client, full_mocks):
        """Ultra-fast start/stop shouldn't deadlock or crash."""
        for _ in range(5):
            resp = client.post("/start_recording")
            assert resp.status_code == 200
            resp = client.post("/stop_recording")
            assert resp.status_code == 200

    def test_report_with_no_audio_captured(self, client, mock_env):
        """If no audio chunks are captured, report should be empty."""
        with patch("app.audio_manager.sd") as mock_sd:
            mock_stream = MagicMock()
            mock_stream.__enter__ = Mock(return_value=mock_stream)
            mock_stream.__exit__ = Mock(return_value=None)
            # Immediately raise so no chunks are captured
            mock_stream.read.side_effect = IOError("No mic")
            mock_sd.InputStream.return_value = mock_stream

            with patch("app.openai_client.client") as mock_oc:
                client.post("/start_recording")
                time.sleep(0.3)
                data = client.post("/stop_recording").json()

                assert data["report"] == ""
                assert data["transcript"] == ""

    def test_large_report_content(self, client, mock_sounddevice, mock_env):
        """Verify that a very large report is stored and returned correctly."""
        large_report = "Section: " + "x" * 50_000
        with patch("app.openai_client.client") as mock_client:
            mock_t = Mock()
            mock_t.text = "Test transcript"
            mock_client.audio.transcriptions.create.return_value = mock_t

            mock_chat = Mock()
            mock_chat.choices = [Mock()]
            mock_chat.choices[0].message.content = large_report
            mock_client.chat.completions.create.return_value = mock_chat

            client.post("/start_recording")
            time.sleep(0.3)
            data = client.post("/stop_recording").json()

            assert len(data["report"]) > 50_000

            # Also verify via polling
            poll_data = client.get("/report").json()
            assert poll_data["report"] == data["report"]


# ===========================================================================
# 11. Integration with transcription worker internals
# ===========================================================================

@pytest.mark.integration
class TestTranscriptionWorkerAutoReport:
    """Test the transcription worker's auto-report generation at the unit level."""

    def test_worker_sets_report_on_state(self, mock_openai, mock_sounddevice):
        """Transcription worker should set report on app state after processing."""
        from app.openai_client import start_transcription_worker

        state = AppState()
        state.stop_event.clear()  # Simulate recording running

        # Add some audio chunks
        for _ in range(5):
            chunk = np.random.rand(1024, 1).astype(np.float32) * 0.1
            state.audio_queue.put(chunk)

        # Signal stop (worker will drain queue and process)
        state.stop_event.set()

        with patch("app.openai_client.client", mock_openai):
            thread = start_transcription_worker(state)
            thread.join(timeout=5)

        assert len(state.get_transcript()) > 0, "Transcript should be set"
        assert len(state.get_report()) > 0, "Report should be auto-generated"

    def test_worker_sets_empty_report_on_gpt_failure(self, mock_sounddevice):
        """If GPT fails, worker should set empty report and not crash."""
        from app.openai_client import start_transcription_worker

        state = AppState()
        state.stop_event.clear()

        for _ in range(3):
            chunk = np.random.rand(1024, 1).astype(np.float32) * 0.1
            state.audio_queue.put(chunk)

        state.stop_event.set()

        with patch("app.openai_client.client") as mock_client:
            mock_t = Mock()
            mock_t.text = "Some transcript"
            mock_client.audio.transcriptions.create.return_value = mock_t
            mock_client.chat.completions.create.side_effect = RuntimeError("GPT down")

            thread = start_transcription_worker(state)
            thread.join(timeout=5)

        assert state.get_transcript() == "Some transcript"
        assert state.get_report() == ""

    def test_worker_handles_empty_queue(self, mock_openai):
        """Worker with no audio in queue should not crash."""
        from app.openai_client import start_transcription_worker

        state = AppState()
        # Queue is empty; immediately signal stop
        state.stop_event.set()

        with patch("app.openai_client.client", mock_openai):
            thread = start_transcription_worker(state)
            thread.join(timeout=3)

        # No audio → no transcript → no report
        assert state.get_transcript() == ""
        assert state.get_report() == ""


# ===========================================================================
# 12. Report content quality checks
# ===========================================================================

@pytest.mark.integration
class TestReportContentQuality:
    """Validate structure and quality of the auto-generated report."""

    def test_report_is_structured_text(self, client, full_mocks):
        """Report should have multiple lines with section headers."""
        client.post("/start_recording")
        time.sleep(0.3)
        data = client.post("/stop_recording").json()
        report = data["report"]

        lines = report.strip().split("\n")
        assert len(lines) > 5, "Report should have multiple lines"

    def test_report_starts_with_title(self, client, full_mocks):
        """Report should start with a title or header."""
        client.post("/start_recording")
        time.sleep(0.3)
        data = client.post("/stop_recording").json()
        report = data["report"].strip()

        assert report.startswith("STRUCTURED MEDICAL REPORT")

    def test_report_has_assessment_and_plan(self, client, full_mocks):
        """Report must include Assessment and Plan sections."""
        client.post("/start_recording")
        time.sleep(0.3)
        data = client.post("/stop_recording").json()
        report = data["report"]

        assert "Assessment" in report
        assert "Plan" in report

    def test_report_does_not_contain_raw_audio_data(self, client, full_mocks):
        """Report should be human-readable text, not binary data."""
        client.post("/start_recording")
        time.sleep(0.3)
        data = client.post("/stop_recording").json()
        report = data["report"]

        # Should not contain null bytes or binary indicators
        assert "\x00" not in report
        assert all(c.isprintable() or c in "\n\r\t" for c in report)
