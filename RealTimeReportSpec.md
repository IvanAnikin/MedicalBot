# Real-Time Voice-to-Report Technical Specification

## Overview
Transform the MedicalBot application to generate medical reports in real-time directly from voice input, eliminating the manual transcription step and simplifying the UI to show only the dynamically generated report.

## Current State
- User starts recording → audio streams to OpenAI Whisper → transcript accumulates → user stops recording → user manually clicks "Generate Report" → structured report is created
- UI has two text areas: one for transcript (right), one for report (left)
- Report generation is a separate manual step after recording stops

## Target State
- User starts recording → audio streams to OpenAI Whisper → transcript accumulates → report is automatically and continuously regenerated in real-time → user sees report updating live
- UI has ONE text area: the dynamically updating structured report
- No manual "Generate Report" button needed
- Report updates in real-time as speech is transcribed

## Architecture Changes

### 1. Backend State Management (`app/state.py`)
**No changes needed** - current state already supports:
- `current_transcript` for storing accumulated transcript
- Thread-safe access with locks
- Could add `current_report` field for caching

### 2. Transcription Worker (`app/openai_client.py`)
**Changes needed:**
- After each transcription update, automatically trigger report generation
- Implement incremental report generation strategy
- Options:
  - **Option A (Simpler):** Regenerate full report after each transcript update
    - Pros: Simple implementation, consistent quality
    - Cons: More API calls, higher latency for long transcripts
  - **Option B (Complex):** Incremental report updates
    - Pros: Fewer full regenerations
    - Cons: Complex state management, may lose context

**Recommendation:** Start with Option A (full regeneration) for reliability

**Implementation:**
```python
def start_transcription_worker(state: AppState):
    def transcribe_audio():
        # ... existing audio buffering code ...
        
        # After finalization, automatically generate report
        if audio_buffer:
            transcript = transcribe_audio_chunks(audio_data)
            state.set_transcript(transcript)
            
            # NEW: Auto-generate report after transcription
            try:
                report = generate_structured_report(transcript)
                state.set_report(report)
            except Exception as e:
                print(f"Error auto-generating report: {e}")
```

### 3. API Endpoints (`main.py`)
**Changes needed:**
- Add new endpoint: `GET /report` - returns current report and recording status
- Modify `POST /stop_recording` - auto-generate report before returning
- Keep `POST /generate_report` for manual regeneration (optional)

**New endpoint:**
```python
@app.get("/report")
async def get_report():
    """Get current report and recording status."""
    return {
        "recording": app_state.is_recording(),
        "report": app_state.get_report(),
        "transcript": app_state.get_transcript()  # Optional, for debugging
    }
```

### 4. Frontend UI (`templates/index.html`)
**Changes needed:**
- Remove transcript textarea from UI
- Keep only report textarea (make it larger/full-width)
- Remove "Generate Report" button
- Modify polling to call `/report` instead of `/transcript`
- Display report updates in real-time during recording

**Layout changes:**
```html
<!-- Single column layout -->
<div class="container single-column">
    <!-- Report Card (full width) -->
    <div class="card">
        <div class="card-title">📋 Medical Report (Live)</div>
        <textarea id="report" placeholder="Start recording to generate report in real-time..."></textarea>
        <div class="helper-text">Report updates automatically as you speak</div>
    </div>
    
    <!-- Controls Card -->
    <div class="card controls-section">
        <div class="card-title">🎙️ Controls</div>
        <div class="button-group">
            <button id="startBtn">Start Recording</button>
            <button id="stopBtn">Stop Recording</button>
            <button id="clearBtn">Clear All</button>
        </div>
    </div>
</div>
```

**JavaScript changes:**
```javascript
function pollReport() {
    recordingState.pollInterval = setInterval(async () => {
        try {
            const data = await apiCall('/report');
            
            // Update report in real-time
            document.getElementById('report').value = data.report || '';
            
            // Stop polling if recording ended
            if (!data.recording) {
                clearInterval(recordingState.pollInterval);
            }
        } catch (error) {
            console.error('Polling error:', error);
        }
    }, config.pollInterval);
}
```

### 5. State Management
**Add to AppState class:**
```python
def __init__(self):
    # ... existing fields ...
    self.current_report: str = ""

def set_report(self, report: str):
    """Update current report."""
    with self._lock:
        self.current_report = report

def get_report(self) -> str:
    """Get current report."""
    with self._lock:
        return self.current_report

def reset(self):
    # ... existing reset code ...
    self.current_report = ""
```

## Implementation Strategy

### Phase 1: Backend Changes
1. Add `current_report` field to AppState
2. Modify transcription worker to auto-generate report after transcription completes
3. Add `/report` endpoint
4. Modify `/stop_recording` to include auto-generated report

### Phase 2: Frontend Changes
1. Remove transcript display from UI
2. Remove "Generate Report" button
3. Update polling logic to fetch report instead of transcript
4. Simplify layout to single-column or full-width report view

### Phase 3: Testing
1. Test with provided audio files (tests/AtTheDoctors.mp3)
2. Test with text input (mock transcription)
3. Verify real-time updates during recording
4. Ensure backwards compatibility with existing tests

## API Changes Summary

### New Endpoint
- `GET /report` - Returns `{ "recording": bool, "report": str, "transcript": str }`

### Modified Endpoints
- `POST /stop_recording` - Now auto-generates and returns report
  - Response: `{ "status": str, "transcript": str, "report": str }`

### Deprecated (Optional)
- `GET /transcript` - Can be kept for debugging or removed
- `POST /generate_report` - Can be kept for manual regeneration or removed

## UI Changes Summary

### Removed Elements
- Transcript textarea (right column)
- "Generate Report" button
- Two-column layout

### Modified Elements
- Report textarea becomes primary/only display
- Update status messages to indicate "Recording & Generating..."
- Helper text changes to "Report updates automatically as you speak"

### New Elements
- Single-column or centered layout
- Larger report textarea (takes full available space)
- Status indicator shows "Generating Report..." during updates

## Testing Strategy

### Unit Tests
- Test auto-report generation in transcription worker
- Test new `/report` endpoint
- Test state management with report field

### Integration Tests
- Test full flow: recording → transcription → auto-report
- Test with real audio file (AtTheDoctors.mp3)
- Test report updates in real-time

### Manual Testing
1. Start application: `python main.py`
2. Open browser: `http://localhost:8000`
3. Click "Start Recording"
4. Speak or play audio file
5. Verify report appears and updates automatically
6. Click "Stop Recording"
7. Verify final report is complete

### Test with Audio File
```python
# Can use existing test file for verification
python tests/test_e2e_mp3_to_report.py
```

## Error Handling

### Transcription Failures
- If transcription fails, show error in status
- Keep existing transcript/report visible
- Allow user to retry

### Report Generation Failures
- If report generation fails, show error in status
- Display transcript as fallback (or keep last valid report)
- Allow manual regeneration via button (optional)

### Edge Cases
- Empty/no speech: Show "No speech detected" message
- Very long recordings: Truncate transcript if needed (OpenAI token limits)
- Network interruptions: Retry with exponential backoff

## Performance Considerations

### API Call Optimization
- Current approach: One transcription call per recording session
- No change needed - report generation happens once after transcription completes
- Future optimization: Could batch smaller audio chunks for more frequent updates

### UI Responsiveness
- Polling interval: 500ms (configurable)
- Report updates should be smooth and non-disruptive
- Use CSS transitions for smooth text updates (optional)

### Memory Management
- Clear audio queue after transcription
- Release thread resources after recording stops
- Keep only current transcript and report in memory

## Configuration

### Environment Variables (Unchanged)
```
OPENAI_API_KEY=sk-...
OPENAI_TRANSCRIPTION_MODEL=whisper-1
OPENAI_CHAT_MODEL=gpt-4o-mini
APP_PORT=8000
```

### Frontend Config (Updated)
```javascript
const config = {
    pollInterval: 500,  // Poll for report updates every 500ms
    apiBase: ''
};
```

## Rollback Plan

If real-time generation causes issues:
1. Keep `/transcript` endpoint
2. Keep "Generate Report" button
3. Make auto-generation optional (feature flag)
4. Allow toggling between modes

## Future Enhancements (Out of Scope for v1)

1. **True streaming**: Update report during recording (requires chunked transcription)
2. **Progress indicator**: Show "Transcribing..." vs "Generating Report..." states
3. **Report sections**: Highlight which section is being updated
4. **Manual editing**: Allow users to edit report inline
5. **Save/Export**: Add download button for report
6. **Templates**: Multiple report templates per specialty
7. **Voice commands**: "Generate report now", "Stop and save"

## Success Criteria

✅ User starts recording and sees report being generated automatically
✅ No manual "Generate Report" step required
✅ UI shows only the report (single text window)
✅ Report updates in real-time or near-real-time
✅ Works with test audio files
✅ Works with text input (for testing)
✅ All existing tests pass
✅ No regressions in core functionality

## Implementation Timeline

1. **Backend changes** - 30 minutes
   - Add report field to state
   - Modify transcription worker
   - Add /report endpoint

2. **Frontend changes** - 30 minutes
   - Remove transcript display
   - Update polling logic
   - Simplify layout

3. **Testing** - 30 minutes
   - Test with audio files
   - Test with text input
   - Run test suite

4. **Documentation** - 15 minutes
   - Update README
   - Update SETUP.md

**Total estimated time: 2 hours**
