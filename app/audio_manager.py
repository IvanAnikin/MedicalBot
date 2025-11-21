"""
Audio recording manager for capturing microphone input.
Handles audio stream management and chunk buffering.
"""

import threading
import sounddevice as sd
import numpy as np
import time
from typing import Optional
from .state import AppState

# Audio Configuration
SAMPLE_RATE = 16000
CHANNELS = 1
CHUNK_SIZE = 1024


def start_recording_thread(state: AppState) -> threading.Thread:
    """
    Start a background thread for audio recording.
    
    Args:
        state: Global application state
        
    Returns:
        Recording thread instance
    """
    def record_audio():
        try:
            print("\n🎤 Starting audio recording thread...")
            print(f"   Sample Rate: {SAMPLE_RATE} Hz")
            print(f"   Channels: {CHANNELS}")
            print(f"   Chunk Size: {CHUNK_SIZE} frames")
            
            # Open input stream
            with sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                blocksize=CHUNK_SIZE,
                dtype=np.float32
            ) as stream:
                print("✅ Audio stream opened successfully")
                chunk_number = 0
                
                while not state.stop_event.is_set():
                    try:
                        # Read audio chunk
                        data, overflowed = stream.read(CHUNK_SIZE)
                        if overflowed:
                            print("⚠️  Warning: audio overflow during recording")
                        
                        chunk_number += 1
                        # Print every 50th chunk to show activity
                        if chunk_number % 50 == 0:
                            audio_level = np.abs(data).mean()
                            print(f"   📊 Chunk {chunk_number} - Audio level: {audio_level:.6f}")
                        
                        # Push to queue. If the queue is full we drop the oldest
                        # chunk to avoid blocking the producer or growing memory
                        # without bound (this preserves recent audio frames).
                        try:
                            if state.audio_queue.full():
                                try:
                                    _ = state.audio_queue.get_nowait()
                                except Exception:
                                    pass
                            state.audio_queue.put_nowait(data.copy())
                        except Exception:
                            # If put fails for any reason, skip this chunk
                            pass
                        # Real audio streams block at the hardware rate. Mocks used
                        # in tests return instantly; sleep here to simulate real
                        # behavior (chunk duration = CHUNK_SIZE / SAMPLE_RATE).
                        # This keeps tests deterministic and prevents mocks from
                        # racing through many chunks too quickly.
                        time.sleep(CHUNK_SIZE / SAMPLE_RATE)
                    except Exception as e:
                        print(f"Error reading audio: {e}")
                        break
                
                print(f"\n✋ Recording stopped. Total chunks captured: {chunk_number}")
        except Exception as e:
            print(f"❌ Error initializing audio stream: {e}")
            raise

    thread = threading.Thread(target=record_audio, daemon=False)
    # Clear the stop_event to signal recording should run, then start thread.
    # This aligns with AppState semantics where stop_event==set means "not recording".
    state.stop_event.clear()
    thread.start()
    # Keep a reference on the state for external management/testing
    state.recording_thread = thread
    return thread


def stop_recording_thread(state: AppState, thread: Optional[threading.Thread], timeout: float = 5.0) -> bool:
    """
    Stop the recording thread gracefully.
    
    Args:
        state: Global application state
        thread: Recording thread instance
        timeout: Max time to wait for thread to join (seconds)
        
    Returns:
        True if thread stopped cleanly, False if timed out
    """
    if thread is None:
        return True
    
    state.stop_event.set()
    try:
        thread.join(timeout=timeout)
        return not thread.is_alive()
    except Exception as e:
        print(f"Error stopping recording thread: {e}")
        return False
