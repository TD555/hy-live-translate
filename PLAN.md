# PLAN

## Goal

Listen to a live call on my Windows laptop (NVIDIA GPU). Transcribe spoken Armenian and print an English
translation in the terminal, labelled by speaker, at most **5 s** after each phrase ends. Everything runs locally.

## Approach in one sentence

Cut each audio stream into phrases with a voice-activity detector, then send every phrase through
ASR → (speaker ID) → translation on one GPU worker and print it.

Phrase-level processing keeps the pipeline simple. Each model sees a complete utterance, which suits
Whisper-style ASR, and the latency budget still fits: about 0.5 s of silence to detect the phrase end,
plus about 1–2 s of GPU time.

## Modules (inputs → outputs)

| Module | File | In | Out |
| --- | --- | --- | --- |
| Audio capture | `hylive/audio.py` | a device index (mic or WASAPI loopback) or a WAV file | `AudioChunk`: float32 mono 16 kHz samples, plus the wall-clock time of the last sample |
| Segmentation | `hylive/vad.py` | stream of `AudioChunk` | `Segment`: one phrase of audio, source (`mic`/`system`), start/end wall-clock time |
| ASR | `hylive/asr.py` | 16 kHz float32 audio | Armenian text |
| Speaker ID | `hylive/speakers.py` | phrase audio (system side only) | `Speaker N`, stable for the session |
| Translation | `hylive/translate.py` | Armenian text | English text |
| Output | `hylive/output.py` | timestamp, speaker, HY, EN, timings | printed terminal block |
| Wiring | `hylive/pipeline.py`, `hylive/__main__.py` | CLI flags | running program |

Each module can be imported and tested on its own. The model modules know nothing about audio devices,
and the audio modules know nothing about models.

## Milestones

1. **Walking skeleton.** Replay two WAV files through the full pipeline (`--replay-mic`, `--replay-system`)
   and get the printed output. This proves the models load and run on my GPU.
2. **Live devices.** List devices, capture the mic and WASAPI loopback at the same time, and test with
   a YouTube Armenian video plus my own voice.
3. **Measure ASR.** Build an eval set (FLEURS/Common Voice clips + my own recordings), then compare
   BuzzASR vs Chillarmo turbo vs stock Whisper on WER/CER and time per clip. Pick the model from the numbers.
4. **Speaker labels.** Tune the similarity threshold on a recording with 2–3 known voices.
5. **Latency hardening.** Look at p95 latency during a real call, plus what happens when both sides talk at once.
6. **Rehearsal.** Run a real call with two people on the other side, then write up limitations in the README.

## Risks

| Risk | Why it matters | Mitigation / how I'll know |
| --- | --- | --- |
| Armenian ASR quality | Stock Whisper is weak on Armenian | Fine-tuned model, measured on my own eval set, not just the model card |
| Model doesn't fit VRAM | The BuzzASR checkpoint is about 2B params in fp16 | `--asr-model` flag, so I can fall back to the turbo fine-tune; check `nvidia-smi` |
| Loopback stops sending data when nothing plays | The last phrase would never be "ended" | Inject silence when no audio arrives for 0.25 s (see DECISIONS D8) |
| Short phrases → bad speaker embeddings | "Այո" (yes) alone can't identify a voice | Phrases < 1 s may not create a new speaker or update a centroid |
| Both sides talk at once | One GPU worker processes phrases in order, so a queue builds up | Measure queue wait (printed with timings) |
| Whisper hallucinates on noise/music | Fake lines appear | VAD threshold + minimum phrase length; check in TESTS.md |
| Call audio is compressed (Opus) | ASR/embedding quality drops vs clean clips | Eval also on recorded call audio, not only FLEURS |

## How I'll test

See `TESTS.md`. The requirement checks come from the brief, not from the code. Unit tests in `tests/` cover
the pure logic (segmenter, speaker tracker, text normalisation, output format). `scripts/eval.py` measures
WER/CER and latency on recorded clips.
