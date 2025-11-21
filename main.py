"""
MedicalBot - FastAPI application for medical report generation from voice.
Local application that records audio, transcribes it, and generates structured reports.
"""

import os
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
        Status and final transcript
    """
    print("\n" + "="*60)
    print("🔴 STOP_RECORDING endpoint called")
    print("="*60)
    
    if not app_state.is_recording():
        return {"status": "not_recording", "transcript": ""}
    
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
        
        return {
            "status": "recording_stopped",
            "transcript": transcript
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


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("APP_PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
