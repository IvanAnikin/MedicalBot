# Dynamic Real-Time Report Generation — Technical Specification

## 1. Overview

Transform the MedicalBot from a **batch transcription model** (transcribe-all-after-stop)
to a **periodic incremental model** where the transcript and medical report update
**while the user is still speaking**.

### Current behaviour
```
[Start] → buffer audio chunks → [Stop] → Whisper(all) → GPT(all) → report
```

### Target behaviour
```
[Start] → every ~8 s of audio: Whisper(window) → append transcript → GPT(full transcript) → update report
         while recording continues ...
[Stop]  → final flush of remaining audio → Whisper → GPT → final report
```

---

## 2. Architecture Changes

### 2.1 Transcription Worker (`app/openai_client.py`)

Replace the current `start_transcription_worker()` with a **periodic drain** loop:

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| `TRANSCRIBE_INTERVAL_CHUNKS` | 125 chunks | ~8 s of audio at 16 kHz / 1024 blocksize |
| Whisper call | Per interval | Only new audio since last call |
| GPT call | Per interval | Full accumulated transcript |

**Algorithm:**
1. Accumulate chunks from `state.audio_queue` in a local buffer.
2. Every 125 chunks (~8 s), concatenate the buffer into a WAV, send to Whisper.
3. Append the returned text to `state.current_transcript`.
4. Call `generate_structured_report(full_transcript)` and store in `state.current_report`.
5. Clear the local buffer and continue.
6. On `stop_event`, drain remaining chunks and do one final Whisper + GPT cycle.

### 2.2 Application State (`app/state.py`)

No structural changes. Existing `set_transcript`, `append_transcript`, `set_report`
and their thread-safe locks are sufficient.

### 2.3 Backend Endpoints (`main.py`)

No changes. The existing `GET /report` endpoint already returns
`state.get_report()` and `state.get_transcript()` which the new worker
updates periodically.

### 2.4 Frontend (`templates/index.html`)

- **Live recording mode:** The existing `pollReport()` already polls `/report` every 500 ms.
  Show the live transcript in the right-side transcript panel (currently only used for demo mode).
  Make the panel visible during live recording too.
- **Update `startRecording()`:** Show transcript panel, start polling.
- **Update `pollReport()`:** Write `data.transcript` into the transcript panel and
  `data.report` into the report textarea on each poll tick.
- **Update `stopRecording()`:** Keep panel visible, update final report.

### 2.5 Demo Simulation

Enhance `POST /demo/simulate` to also use periodic GPT calls:

Split the transcript into ~4 chunks on the backend, fire GPT for each partial
transcript in sequence with a delay. The frontend already polls `/report` so
it will pick up intermediate reports automatically.

---

## 3. API Cost & Performance

- **Whisper calls:** ~1 per 8 seconds of recording (was 1 total). A 30-second
  recording = ~4 Whisper calls instead of 1.
- **GPT calls:** Same count as Whisper — one per interval.
- **Latency per cycle:** Whisper ~1-3 s + GPT ~2-4 s = report update every ~11 s
  in the worst case. Subsequent updates are faster because GPT already has context.
- **Cost:** Marginal increase. Whisper is $0.006/min. GPT-4o-mini is very cheap.

---

## 4. Language Detection

The current `transcribe_audio_chunks()` hardcodes `language="en"`. Since the app
is now Czech-focused, we should **auto-detect** language by omitting the
`language` parameter, letting Whisper decide.

---

## 5. Files Changed

| File | Change |
|------|--------|
| `app/openai_client.py` | Rewrite `start_transcription_worker()` with periodic drain loop |
| `app/openai_client.py` | Remove hardcoded `language="en"` from Whisper call |
| `templates/index.html` | Show transcript panel during live recording, update on poll |
| `templates/index.html` | Update demo `runSimulation()` for periodic report updates |
| `main.py` | Update `/demo/simulate` for chunked report generation |
