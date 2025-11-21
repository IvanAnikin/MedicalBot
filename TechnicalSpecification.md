# Medical Report Assistant v1.0 – Technical Specification

## 1. Product Overview

**Name (working):** Medical Report Assistant v1.0  
**Goal:** Enable doctors and nurses to quickly create structured visit reports from dictated speech.

**Key Design Choice:**  
- FastAPI backend runs locally on the doctor's PC.
- Backend (Python) records audio directly from the OS microphone (e.g., using `sounddevice`).
- Frontend (browser) acts as a remote control and display only:
    - **Buttons:** Start / Stop / Generate Report / Clear
    - **Displays:** Live/full transcript and structured report
- **Data Path:**  
    Microphone → Python (FastAPI) → OpenAI → Python → Browser (text only)  
    _No audio flows through the browser._

---

## 2. Scope of v1.0

**In Scope:**
- Local-only app (backend and frontend on the same machine)
- Accessed at `http://localhost:8000/`
- Single user/session at a time (global recording state)
- Backend-driven recording (Python captures audio, streams to OpenAI for transcription)
- No audio upload from browser
- Single-page, dark-mode UI (two-column layout: left = structured report, right = controls + transcript)
- Live or near-live transcript (backend maintains `current_transcript`, browser polls or receives updates)
- Report generation via OpenAI chat model with fixed medical template

**Out of Scope:**
- Multi-user/multi-tenant support
- EMR integration
- Persistent storage of transcripts/audio
- Authentication/user accounts
- Advanced templating per specialty
- Offline/locally-hosted models

---

## 3. High-Level Architecture

### 3.1 Components

- **FastAPI Backend**
    - Serves UI, handles recording control, transcript retrieval, and report generation
    - Background workers for audio capture and transcription

- **Audio Capture & Streaming Layer**
    - Uses Python audio library (e.g., `sounddevice`)
    - Reads audio chunks, pushes to a thread-safe queue

- **OpenAI Transcription Worker**
    - Streams audio chunks to OpenAI STT
    - Updates global `current_transcript`

- **Browser Frontend**
    - Single HTML page (no mic access)
    - Sends control commands, polls for transcript, displays report

---

## 4. Recording & Transcription Flows

### 4.1 Backend State

- `recording_active: bool`
- `recording_thread: Thread | None`
- `transcription_thread: Thread | None`
- `stop_event: threading.Event`
- `audio_queue: queue.Queue`
- `current_transcript: str`

### 4.2 Start Recording (`POST /start_recording`)

- If already recording, return error
- Clear stop event, reset transcript and queue
- Start recording and transcription threads
- Set `recording_active = True`
- Return `{"status": "recording_started"}`

### 4.3 Stop Recording (`POST /stop_recording`)

- If not recording, return `{"status": "not_recording"}`
- Set stop event, finalize transcript, join threads
- Set `recording_active = False`
- Return `{"status": "recording_stopped", "transcript": current_transcript}`

### 4.4 Get Transcript (`GET /transcript`)

- Return `{"recording": <bool>, "transcript": "<current_transcript>"}`
- Frontend polls every 500–1000 ms during/after recording

---

## 5. Report Generation

### 5.1 Endpoint (`POST /generate_report`)

- Input: `{ "transcript": "<text>" }` (optional)
- If transcript missing, use `current_transcript`
- If empty, return 400 error
- Build OpenAI chat request (system message = medical template, user message = transcript)
- Return `{"report": "<structured_report_text>"}`

### 5.2 Prompt/Template

- **Sections:** Patient Identification, Chief Complaint, HPI, PMH/Allergies/Medications, Objective Findings, Assessment, Plan
- **Rules:**  
    - Do not invent information  
    - If missing, write “Not mentioned in transcript.”  
    - Use concise, clinical language

---

## 6. API Overview

| Endpoint                | Method | Input                | Response/Behavior                                 |
|-------------------------|--------|----------------------|---------------------------------------------------|
| `/`                     | GET    | –                    | Serve main HTML UI                                |
| `/start_recording`      | POST   | –                    | Start recording/transcription threads              |
| `/stop_recording`       | POST   | –                    | Stop threads, return transcript                   |
| `/transcript`           | GET    | –                    | Return current transcript and recording state     |
| `/generate_report`      | POST   | `{ "transcript": ...}` (optional) | Return structured report or error      |

---

## 7. UI Specification

### 7.1 Layout

- **Header:** App name, status pill (Ready / Recording / Error)
- **Main (Two Columns):**
    - **Left:** Structured Report (editable textarea)
    - **Right:** Controls (Start/Stop/Generate/Clear), status, error banner, transcript textarea

### 7.2 Button Behavior

- **Start:** POST `/start_recording`, update UI, begin polling transcript
- **Stop:** POST `/stop_recording`, update UI, finalize transcript
- **Generate Report:** POST `/generate_report`, display report
- **Clear:** Clear transcript/report locally (optionally reset backend)

### 7.3 Dark Mode Styling

- Dark gradient background, rounded cards, soft borders/shadows, accent color for active elements, responsive layout

---

## 8. Configuration & Environment

- **Dependencies:** `fastapi`, `uvicorn`, `openai`, `sounddevice`, `numpy`, `python-multipart`, `jinja2`
- **Environment Variables:**
    - `OPENAI_API_KEY` (required)
    - `OPENAI_TRANSCRIPTION_MODEL` (optional, default: e.g., `gpt-4o-transcribe`)
    - `OPENAI_CHAT_MODEL` (optional, default: e.g., `gpt-5.1-mini`)
    - `APP_PORT` (optional, default: 8000)
- **Audio Settings:** 16kHz, mono, 1024-frame chunks, default input device

---

## 9. Error Handling & Privacy

- **Error Handling:**
    - Mic errors: return error JSON, show frontend banner
    - OpenAI errors: log details, return clean error messages
    - Thread management: always set `recording_active = False` on exit
- **Privacy:**
    - Only OpenAI receives data (audio/text)
    - No local persistence in v1
    - Minimal logging (no content, only metadata)

---

## 10. Non-Functional Requirements

- **Performance:** Non-blocking endpoints, near-real-time transcription
- **Robustness:** Cleanly handle failures, allow restart
- **Maintainability:**  
    - Recording/transcription logic: `audio_manager.py`
    - OpenAI helpers: `openai_client.py`
    - FastAPI routes: `main.py`
    - HTML/JS/CSS: `templates/index.html`
