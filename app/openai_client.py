"""
OpenAI integration for transcription and report generation.
Handles streaming transcription and structured medical report generation.
"""

import os
import threading
import queue
import io
import wave
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
    Streams audio chunks from queue to OpenAI and updates transcript.
    
    Args:
        state: Global application state
        
    Returns:
        Transcription worker thread
    """
    def transcribe_audio():
        try:
            audio_buffer = []
            chunk_count = 0
            
            print("\n🎙️ Transcription worker started - listening for audio chunks...")
            
            while not state.stop_event.is_set():
                try:
                    # Get audio chunk with timeout
                    try:
                        chunk = state.audio_queue.get(timeout=0.5)
                        audio_buffer.append(chunk)
                        chunk_count += 1
                        # Print status every 10 chunks to avoid spam
                        if chunk_count % 10 == 0:
                            print(f"📍 Captured {chunk_count} audio chunks so far...")
                    except queue.Empty:
                        continue
                    
                except Exception as e:
                    print(f"Error processing audio chunk: {e}")
                    continue
            
            # Process remaining audio
            while not state.audio_queue.empty():
                try:
                    chunk = state.audio_queue.get_nowait()
                    audio_buffer.append(chunk)
                    chunk_count += 1
                except queue.Empty:
                    break
            
            # Finalize transcription if we have audio
            if audio_buffer:
                print(f"\n✅ Recording stopped. Total chunks captured: {chunk_count}")
                print(f"📊 Total audio duration: {len(audio_buffer) * 1024 / 16000:.2f} seconds")
                try:
                    audio_data = np.concatenate(audio_buffer)
                    print(f"🔊 Audio data shape: {audio_data.shape}")
                    print(f"🔊 Audio min: {audio_data.min():.4f}, max: {audio_data.max():.4f}, mean: {audio_data.mean():.4f}")
                    print(f"📤 Sending to OpenAI Whisper for transcription...")
                    transcript = transcribe_audio_chunks(audio_data)
                    print(f"✨ Transcription received:\n{transcript}\n")
                    state.set_transcript(transcript)
                except Exception as e:
                    print(f"❌ Error finalizing transcription: {e}")
            else:
                print("\n⚠️  No audio captured - audio buffer is empty!")
                    
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
        
        # Create transcript
        transcript = client.audio.transcriptions.create(
            model=get_transcription_model(),
            file=("audio.wav", wav_data),
            language="en"
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
    
    system_prompt = """You are a medical documentation specialist. Your task is to convert the given patient visit transcript into a structured medical report with the following sections:

1. **Patient Identification** - Name, age, date of visit
2. **Chief Complaint / Reason for Visit** - Why the patient came
3. **History of Present Illness (HPI)** - Details about current symptoms
4. **Past Medical History / Allergies / Medications** - Relevant history and current medications
5. **Objective Findings** - Vital signs, examination findings
6. **Assessment** - Clinical impression and diagnosis
7. **Plan** - Treatment plan and follow-up

Rules:
- Do NOT invent information that is not in the transcript
- If information for a section is missing, write: "Not mentioned in transcript"
- Use concise, clinical language
- Format clearly with section headers

Return only the structured report, no additional commentary."""

    try:
        response = client.chat.completions.create(
            model=get_chat_model(),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Please convert this transcript into a structured medical report:\n\n{transcript}"}
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
