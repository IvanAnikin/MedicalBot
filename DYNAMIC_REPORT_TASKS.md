# Dynamic Report — Implementation Plan & Tasks

## Phase 1: Backend — Periodic Transcription Worker
- [x] Task 1.1: Rewrite `start_transcription_worker()` with periodic drain loop
  - Accumulate chunks, every ~125 chunks (~8s) call Whisper on the new audio
  - Append result to `state.current_transcript`
  - Call `generate_structured_report()` with full transcript
  - Store result in `state.current_report`
  - On stop_event: flush remaining audio, final Whisper + GPT cycle
- [x] Task 1.2: Remove hardcoded `language="en"` from `transcribe_audio_chunks()`
  - Let Whisper auto-detect language (supports Czech + English)

## Phase 2: Frontend — Live Transcript & Report During Recording
- [x] Task 2.1: Show transcript panel during live recording
  - Make transcript side panel visible on `startRecording()`
  - Update transcript text + report textarea on each poll tick
- [x] Task 2.2: Update `pollReport()` to write transcript + report live
  - Write `data.transcript` to transcript panel
  - Write `data.report` to report textarea
  - Show status updates ("Přepisuji...", "Aktualizuji zprávu...")
- [x] Task 2.3: Update `stopRecording()` to show final state
  - Keep panel visible, update with final transcript, show "Dokončeno"

## Phase 3: Demo Simulation — Periodic Report Updates
- [x] Task 3.1: Update `/demo/simulate` endpoint for chunked generation
  - Split transcript into ~4 parts
  - Generate intermediate reports for each chunk with delays
  - Frontend already polls so it picks up updates automatically
- [x] Task 3.2: Update `runSimulation()` in frontend
  - Start report polling immediately when simulation begins
  - Report textarea updates live while transcript types out

## Phase 4: Testing & Verification
- [x] Task 4.1: Restart server and verify live recording works
- [x] Task 4.2: Verify demo simulation shows incremental report updates
