# DECISIONS

A short log of each decision, why it was made, and what would change it. Status is either
**proposed** (Claude suggested it, and it isn't yet confirmed by me or by measurement) or **confirmed**.

---

### D1. Capture system audio with WASAPI loopback (PyAudioWPatch)
**Status:** proposed
**Why:** On Windows, WASAPI can record any output device in loopback mode, so no virtual cable is needed and
I still hear the call normally. PyAudioWPatch is a PyAudio fork that exposes these loopback devices as extra
input devices. The same library also opens the mic, so there is one audio API for both sources.
**Alternatives:** VB-Audio Virtual Cable (an extra install, and you have to route the call app to it),
`sounddevice` (no loopback support in the standard PortAudio build), Stereo Mix (not present on many laptops).
**Revisit if:** loopback drops or clicks under load.

### D2. Process VAD-segmented phrases, not a streaming ASR
**Status:** proposed
**Why:** The brief measures latency from the *end of a phrase*. Waiting for the phrase to end (≈0.5 s of
silence) and then transcribing the whole phrase keeps the pipeline simple, and it fits in 5 s when GPU
inference takes about 1–2 s. Whisper models are trained on whole utterances, and splitting a phrase in the
middle hurts accuracy.
**Alternatives:** WhisperLiveKit / SimulStreaming (partial results appear sooner, but many more moving parts,
and they're built around stock Whisper checkpoints).
**Revisit if:** speakers talk in long phrases without pauses. Phrases are force-cut at `--max-segment`
(default 12 s).

### D3. ASR model: `BuzzASR/armenian` by default, to be confirmed by my own eval
**Status:** proposed (numbers below are from the model cards, not measured by me yet)
| Candidate | What it is | Reported result |
| --- | --- | --- |
| `BuzzASR/armenian` | whisper-large-v3, full fine-tune with an Armenian-specific tokenizer (EMNLP 2026 Findings) | CER 3.72 / WER 11.89 on FLEURS; CER 2.28 / WER 7.51 combined with CV25 |
| `Chillarmo/whisper-large-v3-turbo-armenian` | large-v3-turbo (fewer decoder layers → faster) fine-tuned on Common Voice 20 | to measure |
| `openai/whisper-large-v3` (zero-shot) | baseline | CER 15.53 combined (per the BuzzASR card); WER 44.4% (ElevenLabs page — a competitor, treat as rough) |
| small/tiny Armenian fine-tunes | e.g. `Edmon02/whisper-small-hy` | ~75% WER, not usable |

**Why:** BuzzASR has by far the best reported numbers, and its evaluation includes FLEURS, which is not just
read Common Voice text. Note: it replaces the tokenizer, so it may not convert to faster-whisper/CTranslate2.
I run it with plain `transformers`, using the card's own generation settings (`num_beams=1,
no_repeat_ngram_size=3, repetition_penalty=1.2`, with the language prompt baked into the generation config).
**Revisit if:** my eval shows the turbo model is close in WER and much faster, or BuzzASR doesn't fit VRAM.
**Measured 2026-10-29/30 (RTX 4060 Laptop 8 GB, plugged in):** all three models use 4.1 GiB of GPU memory.
ASR takes 0.4–0.9 s for a 1–3 s phrase and 2.2–3.6 s for a 12 s phrase. There's no speed reason to switch;
accuracy still needs the eval set. (A first run looked 3× slower because a model was downloading in the background.)

### D4. Translation: NLLB-200 (`facebook/nllb-200-distilled-600M` by default)
**Status:** proposed
**Why:** NLLB is a dedicated MT model covering Armenian (`hye_Armn`). It's small and fast on a GPU, and
it's easy to switch to 1.3B/3.3B with a flag. Licence is CC-BY-NC, which is fine for this challenge.
**Alternatives:** MADLAD-400 (3B+, slower), a local LLM such as Qwen/Gemma (better at fluent English when it
understands, but weak on Armenian and much slower to start).
**Revisit if:** the English is not understandable on my eval phrases. The first thing to try is 1.3B.
**Finding 2026-10-30 (live interview test):** once, the output looped ("I'm in rap, I'm in rap, …", 4 s of compute),
and on long multi-sentence inputs it dropped half the content. **Change:** split the text into sentences and
translate them as one batch, add `no_repeat_ngram_size=4`, and limit the output to 2× the input length.
To verify on a replay of the same recording.

### D5. Speaker ID: one ECAPA embedding per phrase + online clustering
**Status:** proposed
**Why:** VAD already gives me phrases, and each phrase is (almost always) one speaker. So I compute a
192-dim embedding per phrase (`speechbrain/spkrec-ecapa-voxceleb`, not gated, no HF token) and assign it
to the most similar known speaker if cosine similarity ≥ threshold; otherwise I create a new speaker.
That is about 60 lines of testable code.
**Alternatives:** diart (real streaming diarization, but pyannote gated models, RxPY, and more latency to
tune), pyannote 3.x offline pipeline (not streaming).
**Known weakness:** two people inside one phrase (quick back-and-forth) get a single label.
**Revisit if:** labels flip often in the rehearsal call.
**Finding 2026-10-30 (live, two-person YouTube interview): FAILS.** Every call-side line was `Speaker 1` (sim 0.49–0.81).
Cause: the speakers hand over without a 0.5 s pause, so most phrases were force-cut at 12 s (`vad` ≈ 0.02 s in
the timings) and contained both voices. Their embeddings are mixtures, and all look alike. So the main problem is
*segments with two voices*, not the threshold. Next: record the clip (`scripts/record.py`), then compare fixes on
replay — (a) a shorter `--min-silence` / `--max-segment` plus a higher `--spk-threshold`; (b) per-window
embeddings inside a segment, splitting at speaker changes; (c) pyannote segmentation (gated model, HF token).

### D6. One GPU worker, phrases processed in order
**Status:** proposed
**Why:** It's simple, and the order of printed lines matches the order of speech. Running two models on one
GPU in parallel barely speeds things up.
**Revisit if:** queue wait shows up as a large part of latency when both sides talk.

### D7. Fail loudly, no silent fallbacks
**Status:** proposed
If CUDA is not available, the program stops (unless `--device cpu` is passed explicitly). If a device index
is wrong, it stops with the device list. If a model fails to load, it raises. Every line prints its timings,
so slow stages are visible.

### D8. Inject silence when the loopback stream stops delivering audio
**Status:** proposed
**Why:** WASAPI loopback sends no packets when nothing is playing. Without packets, the VAD never sees the
silence after the last phrase, so that phrase would only be printed when someone speaks again. When no
audio arrives for 0.25 s, the segmenter is fed 0.25 s of zeros. This is deliberate and only affects silence.
