"""
MedicalBot - FastAPI application for medical report generation from voice.
Local application that records audio, transcribes it, and generates structured reports.
"""

import os
import threading
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import FileResponse
from starlette.requests import Request
from dotenv import load_dotenv

from app.state import app_state
from app.audio_manager import start_recording_thread, stop_recording_thread
from app.openai_client import start_transcription_worker, generate_structured_report

# Load environment variables
load_dotenv()

# Validate required configuration
if not os.getenv("OPENAI_API_KEY"):
    raise ValueError("OPENAI_API_KEY environment variable is required")

# Initialize FastAPI app
app = FastAPI(title="MedicalBot", version="1.0.0")

# Configure templates
templates = Jinja2Templates(directory="templates")

# Mount static files
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def index(request: Request):
    """Serve main HTML UI."""
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/start_recording")
async def start_recording():
    """
    Start recording and transcription.
    
    Returns:
        Status message or error (409 if already recording)
    """
    if app_state.is_recording():
        raise HTTPException(status_code=409, detail="Recording already in progress")
    
    try:
        print("\n" + "="*60)
        print("🟢 START_RECORDING endpoint called")
        print("="*60)
        
        # Reset state
        app_state.reset()
        app_state.set_recording_active(True)
        
        # Start recording thread
        app_state.recording_thread = start_recording_thread(app_state)
        
        # Start transcription worker thread
        app_state.transcription_thread = start_transcription_worker(app_state)
        
        print("✅ Recording and transcription threads started")
        return {"status": "recording_started"}
    except Exception as e:
        app_state.set_recording_active(False)
        print(f"❌ Error starting recording: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start recording: {str(e)}")


@app.post("/stop_recording")
async def stop_recording():
    """
    Stop recording and transcription.
    
    Returns:
        Status, final transcript, and auto-generated report
    """
    print("\n" + "="*60)
    print("🔴 STOP_RECORDING endpoint called")
    print("="*60)
    
    if not app_state.is_recording():
        return {
            "status": "not_recording",
            "transcript": "",
            "report": ""
        }
    
    try:
        # Signal stop event
        app_state.stop_event.set()
        
        # Wait for threads to finish
        if app_state.recording_thread:
            stop_recording_thread(app_state, app_state.recording_thread)
        
        if app_state.transcription_thread:
            app_state.transcription_thread.join(timeout=10)
        
        app_state.set_recording_active(False)
        transcript = app_state.get_transcript()
        report = app_state.get_report()
        
        return {
            "status": "recording_stopped",
            "transcript": transcript,
            "report": report
        }
    except Exception as e:
        app_state.set_recording_active(False)
        raise HTTPException(status_code=500, detail=f"Error stopping recording: {str(e)}")


@app.get("/transcript")
async def get_transcript():
    """
    Get current transcript and recording status.
    
    Returns:
        Recording status and current transcript
    """
    return {
        "recording": app_state.is_recording(),
        "transcript": app_state.get_transcript()
    }


@app.get("/report")
async def get_report():
    """
    Get current report and recording status.
    
    Returns:
        Recording status, current report, and transcript
    """
    return {
        "recording": app_state.is_recording(),
        "report": app_state.get_report(),
        "transcript": app_state.get_transcript()
    }


@app.post("/generate_report")
async def generate_report(request_data: dict = None):
    """
    Generate structured medical report from transcript.
    
    Args:
        request_data: Optional dict with "transcript" field
        
    Returns:
        Structured report or error
    """
    try:
        # Get transcript from request or use current
        if request_data and "transcript" in request_data:
            transcript = request_data["transcript"]
        else:
            transcript = app_state.get_transcript()
        
        if not transcript or not transcript.strip():
            raise HTTPException(status_code=400, detail="Transcript is empty")
        
        report = generate_structured_report(transcript)
        
        return {"report": report}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating report: {str(e)}")


@app.post("/reset_session")
async def reset_session():
    """
    Reset session state and clear transcript.
    
    Returns:
        Status message
    """
    try:
        app_state.stop_event.set()
        
        if app_state.recording_thread and app_state.recording_thread.is_alive():
            app_state.recording_thread.join(timeout=5)
        
        if app_state.transcription_thread and app_state.transcription_thread.is_alive():
            app_state.transcription_thread.join(timeout=5)
        
        app_state.reset()
        
        return {"status": "session_reset"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error resetting session: {str(e)}")


# ---------------------------------------------------------------------------
# Demo / Presentation Mode Endpoints
# ---------------------------------------------------------------------------

DEMO_SCENARIOS_DIR = Path(__file__).parent / "demo_scenarios"


@app.get("/demo/scenarios")
async def list_demo_scenarios():
    """
    List available demo scenario text files.

    Returns:
        List of scenario objects with id, name and preview.
    """
    scenarios = []
    if DEMO_SCENARIOS_DIR.exists():
        for f in sorted(DEMO_SCENARIOS_DIR.glob("*.txt")):
            text = f.read_text(encoding="utf-8").strip()
            # Build a human-friendly name from the filename
            raw = f.stem
            # Czech scenario names (cz_ prefix)
            _CZ_NAMES = {
                "cz_kardialni_nahoda": "🇨🇿 Kardiální nehoda",
                "cz_respiracni_infekce": "🇨🇿 Respirační infekce",
                "cz_detska_prohlidka": "🇨🇿 Dětská prohlídka",
                "cz_otrava_jidlem": "🇨🇿 Otrava jídlem",
            }
            name = _CZ_NAMES.get(raw, raw.replace("_", " ").title())
            preview = text[:120] + ("..." if len(text) > 120 else "")
            scenarios.append({
                "id": f.stem,
                "name": name,
                "preview": preview,
                "length": len(text.split()),
            })
    return {"scenarios": scenarios}


@app.post("/demo/simulate")
async def demo_simulate(request_data: dict):
    """
    Run a demo scenario with **incremental report generation**.

    Splits the transcript into ~4 chunks and generates a report after each
    chunk with a small delay, so the frontend sees the report evolving
    in real time as the transcript panel types out words.

    Args:
        request_data: {"scenario_id": "<filename stem>"}

    Returns:
        {"status": "simulating", "transcript": "<full text>"}
    """
    scenario_id = request_data.get("scenario_id")
    if not scenario_id:
        raise HTTPException(status_code=400, detail="scenario_id is required")

    scenario_file = DEMO_SCENARIOS_DIR / f"{scenario_id}.txt"
    if not scenario_file.exists():
        raise HTTPException(status_code=404, detail=f"Scenario '{scenario_id}' not found")

    transcript = scenario_file.read_text(encoding="utf-8").strip()

    # Reset state
    app_state.reset()
    app_state.set_recording_active(True)  # UI shows "working" state

    # Generate reports incrementally in background
    def _incremental_generate():
        import time
        try:
            words = transcript.split()
            num_chunks = 4
            chunk_size = max(1, len(words) // num_chunks)

            for i in range(num_chunks):
                start = 0
                end = min((i + 1) * chunk_size, len(words))
                if i == num_chunks - 1:
                    end = len(words)  # last chunk gets everything remaining

                partial_transcript = " ".join(words[start:end])
                app_state.set_transcript(partial_transcript)

                print(f"📋 Demo: generating report for chunk {i+1}/{num_chunks} "
                      f"({end}/{len(words)} words)...")
                try:
                    report = generate_structured_report(partial_transcript)
                    app_state.set_report(report)
                    print(f"✅ Demo: chunk {i+1} report updated")
                except Exception as e:
                    print(f"❌ Demo: chunk {i+1} report error: {e}")

                if i < num_chunks - 1:
                    # Wait between chunks — roughly matches typing animation speed
                    # ~80ms per word × chunk_size words
                    delay = min(chunk_size * 0.08, 8.0)
                    time.sleep(delay)

        except Exception as e:
            print(f"❌ Demo incremental generation error: {e}")
            app_state.set_report(f"Error: {e}")
        finally:
            app_state.set_transcript(transcript)  # ensure full transcript is set
            app_state.set_recording_active(False)

    t = threading.Thread(target=_incremental_generate, daemon=True)
    t.start()

    return {
        "status": "simulating",
        "transcript": transcript,
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("APP_PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
