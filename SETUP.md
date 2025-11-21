# MedicalBot - Setup & Development Guide

## ✅ Project Setup Complete!

Your MedicalBot project has been initialized with all Phase 0 requirements.

---

## 📁 Project Structure

```
MedicalBot/
├── venv/                          # Virtual environment (created)
├── app/                           # Python package
│   ├── __init__.py               # Package marker
│   ├── state.py                  # Global recording state
│   ├── audio_manager.py          # Audio recording management
│   └── openai_client.py          # OpenAI integration
├── templates/
│   └── index.html                # Frontend UI (dark mode, responsive)
├── static/                       # Placeholder for future assets
├── main.py                       # FastAPI application entrypoint
├── requirements.txt              # Python dependencies (frozen versions)
├── .env                          # Configuration (local - DO NOT COMMIT)
├── .env.example                  # Configuration template
├── .gitignore                    # Git exclusions
├── README.md                     # Project overview
├── TechnicalSpecification.md     # System design
└── ToDos.md                      # Development tasks
```

---

## 🚀 Quick Start

### 1. Configure OpenAI API Key

Edit `.env` file and add your OpenAI API key:

```bash
# .env
OPENAI_API_KEY=sk-your-actual-key-here
OPENAI_TRANSCRIPTION_MODEL=whisper-1
OPENAI_CHAT_MODEL=gpt-4o-mini
APP_PORT=8000
```

### 2. Activate Virtual Environment

```bash
cd /Users/ivananikin/Documents/MedicalBot
source venv/bin/activate
```

### 3. Run the Application

```bash
python main.py
```

The server will start on `http://localhost:8000/`

---

## 📦 Installed Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `fastapi` | 0.104.1 | Web framework |
| `uvicorn[standard]` | 0.24.0 | ASGI server with optimizations |
| `openai` | 1.3.8 | OpenAI API client |
| `sounddevice` | 0.4.6 | Microphone input |
| `numpy` | 1.24.3 | Audio array processing |
| `jinja2` | 3.1.2 | Template rendering |
| `python-multipart` | 0.0.6 | FastAPI form handling |
| `python-dotenv` | 1.0.0 | Environment variable loading |

---

## 🔧 Core Components

### 1. **app/state.py** - Global State Management
- Thread-safe state container
- Manages recording active flag, stop events, audio queue
- Thread-safe transcript storage

### 2. **app/audio_manager.py** - Audio Recording
- Captures audio from default input device
- Configurable: 16kHz, mono, 1024 frame chunks
- Graceful thread lifecycle management

### 3. **app/openai_client.py** - OpenAI Integration
- Transcription worker (streams audio to Whisper)
- Report generation (structured medical template)
- Error handling with clear messages

### 4. **main.py** - FastAPI Routes
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/` | GET | Serve UI |
| `/start_recording` | POST | Begin recording |
| `/stop_recording` | POST | End recording, return transcript |
| `/transcript` | GET | Poll current transcript |
| `/generate_report` | POST | Generate structured report |
| `/reset_session` | POST | Clear state |

### 5. **templates/index.html** - Frontend
- Dark mode design with CSS variables
- 2-column layout (report + controls)
- Real-time transcript polling
- Error handling & status indicators
- Responsive mobile support

---

## 🧪 Testing the Setup

### Verify Dependencies
```bash
source venv/bin/activate
pip list
```

### Verify Syntax
```bash
python -m py_compile main.py app/*.py
```

### Import Check
```bash
python -c "import fastapi, openai, sounddevice; print('✅ All imports working')"
```

---

## 🎯 Next Steps (Phase 1+)

You're now ready to proceed with development phases:

- **Phase 1:** Verify state management and audio recording thread
- **Phase 2:** Test OpenAI transcription integration
- **Phase 3:** Validate API endpoints
- **Phase 4:** Test frontend UI interaction
- **Phase 5:** Polish and iterate

---

## ⚠️ Important Notes

### Environment Variables
- `.env` file is in `.gitignore` - never commit it
- Always use `.env.example` as a template for new devs
- Required: `OPENAI_API_KEY`
- Optional: API models and port (have sensible defaults)

### Audio Configuration
- **Sample Rate:** 16000 Hz
- **Channels:** 1 (mono)
- **Chunk Size:** 1024 frames
- **Default Device:** Uses OS default input device

### Thread Safety
- All state access is protected by locks
- Recording/transcription threads are daemon=False (clean shutdown)
- Thread joins have 5-10 second timeouts

---

## 🐛 Troubleshooting

### Microphone Not Detected
```python
import sounddevice
print(sounddevice.default)  # Check default device
print(sounddevice.query_devices())  # List all devices
```

### OpenAI API Errors
- Verify `OPENAI_API_KEY` is set and valid
- Check OpenAI account has Whisper API access
- Verify rate limits not exceeded

### Port Already in Use
```bash
# Use different port
APP_PORT=8001 python main.py
```

---

## 📝 Configuration Reference

### .env Variables

```bash
# OpenAI (Required)
OPENAI_API_KEY=sk-...

# OpenAI Models (Optional - has defaults)
OPENAI_TRANSCRIPTION_MODEL=whisper-1
OPENAI_CHAT_MODEL=gpt-4o-mini

# Application (Optional - defaults to 8000)
APP_PORT=8000
```

---

## 🔒 Security Notes

- No audio stored locally
- Only OpenAI receives audio/transcripts
- API key never logged or exposed
- `.env` file gitignored
- Minimal logging (metadata only)

---

## 📚 Documentation Files

- **README.md** - Project overview
- **TechnicalSpecification.md** - System architecture & API design
- **ToDos.md** - Development phases & checklist
- **This file (SETUP.md)** - Installation & configuration guide

---

**Ready to start development!** 🚀
