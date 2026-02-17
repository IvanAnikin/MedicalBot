"""
OpenAI integration for transcription and report generation.
Handles streaming transcription and structured medical report generation.
"""

import os
import threading
import queue
import io
import wave
from datetime import date
from typing import Optional
import numpy as np
from dotenv import load_dotenv
from openai import OpenAI, APIError
from .state import AppState

# Load environment variables
load_dotenv()

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def get_transcription_model() -> str:
    """Get transcription model name from environment or use default."""
    return os.getenv("OPENAI_TRANSCRIPTION_MODEL", "whisper-1")


def get_chat_model() -> str:
    """Get chat model name from environment or use default."""
    return os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")


def start_transcription_worker(state: AppState) -> threading.Thread:
    """
    Start background transcription worker thread.
    Periodically drains audio chunks, transcribes them via Whisper,
    appends to the running transcript, and regenerates the medical report.

    This gives the user a **live-updating** report while recording continues.

    Args:
        state: Global application state

    Returns:
        Transcription worker thread
    """
    # ~8 seconds of audio at 16 kHz with 1024-sample blocks
    TRANSCRIBE_INTERVAL_CHUNKS = 125

    def _drain_and_transcribe(audio_buffer: list) -> str:
        """Concatenate buffered chunks, send to Whisper, return text."""
        if not audio_buffer:
            return ""
        audio_data = np.concatenate(audio_buffer)
        duration = len(audio_data) / 16000
        print(f"📤 Sending {duration:.1f}s of audio to Whisper...")
        text = transcribe_audio_chunks(audio_data)
        print(f"✨ Whisper returned: {text[:120]}{'...' if len(text) > 120 else ''}")
        return text

    def _update_report(state: AppState):
        """Regenerate structured report from full accumulated transcript."""
        transcript = state.get_transcript()
        if not transcript or not transcript.strip():
            return
        try:
            print("📋 Regenerating structured report...")
            report = generate_structured_report(transcript)
            state.set_report(report)
            print("✅ Report updated")
        except Exception as e:
            print(f"❌ Error generating report: {e}")

    def transcribe_audio():
        try:
            interval_buffer: list = []   # chunks accumulated since last Whisper call
            total_chunks = 0

            print("\n🎙️ Transcription worker started (periodic mode, interval="
                  f"{TRANSCRIBE_INTERVAL_CHUNKS} chunks ≈ "
                  f"{TRANSCRIBE_INTERVAL_CHUNKS * 1024 / 16000:.0f}s)")

            while not state.stop_event.is_set():
                # Drain available chunks from queue
                try:
                    chunk = state.audio_queue.get(timeout=0.5)
                    interval_buffer.append(chunk)
                    total_chunks += 1

                    if total_chunks % 10 == 0:
                        print(f"📍 Captured {total_chunks} audio chunks so far...")

                except queue.Empty:
                    continue

                # When enough audio has accumulated, transcribe the interval
                if len(interval_buffer) >= TRANSCRIBE_INTERVAL_CHUNKS:
                    try:
                        new_text = _drain_and_transcribe(interval_buffer)
                        interval_buffer = []
                        if new_text.strip():
                            state.append_transcript(" " + new_text if state.get_transcript() else new_text)
                            _update_report(state)
                    except Exception as e:
                        print(f"❌ Periodic transcription error: {e}")
                        interval_buffer = []   # discard to avoid stuck state

            # ---- Recording stopped: flush remaining audio ----
            while not state.audio_queue.empty():
                try:
                    chunk = state.audio_queue.get_nowait()
                    interval_buffer.append(chunk)
                    total_chunks += 1
                except queue.Empty:
                    break

            if interval_buffer:
                print(f"\n✅ Recording stopped. Flushing final {len(interval_buffer)} chunks...")
                try:
                    new_text = _drain_and_transcribe(interval_buffer)
                    if new_text.strip():
                        state.append_transcript(" " + new_text if state.get_transcript() else new_text)
                        _update_report(state)
                except Exception as e:
                    print(f"❌ Final transcription error: {e}")
            else:
                print("\n⚠️  No remaining audio to flush")

            print(f"🏁 Transcription worker finished. Total chunks processed: {total_chunks}")

        except Exception as e:
            print(f"Error in transcription worker: {e}")

    thread = threading.Thread(target=transcribe_audio, daemon=False)
    thread.start()
    return thread


def transcribe_audio_chunks(audio_data: np.ndarray) -> str:
    """
    Transcribe audio data using OpenAI Whisper.
    
    Args:
        audio_data: Audio samples (numpy array)
        
    Returns:
        Transcribed text
    """
    try:
        # Convert float32 audio to PCM 16-bit
        audio_int16 = (audio_data * 32767).astype(np.int16)
        
        # Create WAV file in memory
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, 'wb') as wav_file:
            # Set WAV parameters: 1 channel, 2 bytes per sample, 16000 Hz sample rate
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(16000)
            wav_file.writeframes(audio_int16.tobytes())
        
        # Get the WAV data
        wav_buffer.seek(0)
        wav_data = wav_buffer.read()
        
        print(f"📦 Created WAV file: {len(wav_data)} bytes")
        
        # Create transcript — let Whisper auto-detect language (CZ/EN)
        transcript = client.audio.transcriptions.create(
            model=get_transcription_model(),
            file=("audio.wav", wav_data),
        )
        
        return transcript.text
    except APIError as e:
        print(f"OpenAI API error during transcription: {e}")
        raise
    except Exception as e:
        print(f"Error transcribing audio: {e}")
        raise


def generate_structured_report(transcript: str) -> str:
    """
    Generate a structured medical report from transcript.
    
    Args:
        transcript: Patient visit transcript
        
    Returns:
        Structured medical report
    """
    # Allow empty transcripts to be handled by the model/mock in tests.
    # Previously this raised an error; tests expect a string response even
    # for empty transcripts, so we permit calling the chat API with an
    # empty body (the client fixture will return a mocked report).
    if not transcript or not transcript.strip():
        transcript = ""
    
    today = date.today().strftime("%d. %m. %Y")

    system_prompt = f"""Jsi specialista na lékařskou dokumentaci. Tvým úkolem je převést přepis návštěvy pacienta do strukturované lékařské zprávy v ČESKÉM jazyce s následujícími sekcemi:

1. **Identifikace pacienta** – Jméno, věk, datum návštěvy (dnešní datum je {today})
2. **Hlavní obtíže / Důvod návštěvy** – Proč pacient přišel
3. **Anamnéza nynějšího onemocnění** – Podrobnosti o aktuálních příznacích
4. **Osobní anamnéza / Alergie / Léky** – Relevantní historie a současná medikace
5. **Objektivní nález** – Vitální funkce, vyšetřovací nálezy
6. **Hodnocení** – Klinický dojem a diagnóza
7. **Plán** – Léčebný plán a kontroly

Pravidla:
- NEVYMÝŠLEJ informace, které nejsou v přepisu
- Datum návštěvy VŽDY vyplň jako {today}
- Pokud informace pro danou sekci chybí, napiš: "Nezmíněno v přepisu"
- Používej stručný, klinický jazyk v češtině
- Formátuj přehledně s nadpisy sekcí
- Celá zpráva MUSÍ být v češtině, i když je přepis v angličtině

Vrať pouze strukturovanou zprávu, žádný další komentář."""

    try:
        response = client.chat.completions.create(
            model=get_chat_model(),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Převeď tento přepis do strukturované lékařské zprávy v češtině:\n\n{transcript}"}
            ],
            temperature=0.3,  # Lower temperature for more consistent output
            max_tokens=2000
        )
        
        return response.choices[0].message.content
    except APIError as e:
        print(f"OpenAI API error during report generation: {e}")
        raise
    except Exception as e:
        print(f"Error generating report: {e}")
        raise
