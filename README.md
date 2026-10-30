# hy-live-translate

Listens to a live call and prints each spoken Armenian phrase with an English translation, labelled by
speaker (`Me` for my microphone, `Speaker 1`, `Speaker 2`, … for the other side). Everything runs locally
on a Windows laptop with an NVIDIA GPU.

```
[00:01:12] Speaker 1
  HY: Բարև, ինչպե՞ս ես։
  EN: Hi, how are you?
  (latency 1.84s = vad 0.53 + queue 0.00 + asr 0.91 + spk 0.03 + mt 0.37 | sim 0.71)
```

The last line shows the time from the **end of the phrase** to the printed English line, split by stage.
`sim` is the voice similarity used to choose the speaker label. Hide this line with `--no-timings`.

> **Status (2026-10-30):** runs live on my laptop (RTX 4060 Laptop GPU, 8 GB; the models use 4.1 GiB).
> Measured latency, from the end of a phrase to its English line: 0.7–2.5 s on a replayed 3-minute two-person
> interview, 1.1–2.6 s for my own live speech. Mic/system separation works. Call-side speaker labels work
> partly (see *Known limitations*). ASR/MT accuracy figures below still come from model cards, because my own
> eval set isn't built yet.

---

## Setup (Windows 10/11, NVIDIA GPU)

1. **Python 3.10–3.13** in a fresh virtual environment:
   ```
   python -m venv .venv
   .venv\Scripts\activate
   ```
2. **PyTorch with CUDA.** Pick *Windows / Pip / CUDA* at https://pytorch.org/get-started/locally/ and run the
   command it gives (it looks like `pip install torch torchaudio --index-url https://download.pytorch.org/whl/cuXXX`).
   Check it with:
   ```
   python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
   ```
3. **Everything else:**
   ```
   pip install -r requirements.txt
   ```
4. **First run downloads the models** from Hugging Face (about 6–7 GB in total, no account or token needed). After
   that it runs offline. To prove nothing goes to the network, run `$env:HF_HUB_OFFLINE=1` in PowerShell
   (`set HF_HUB_OFFLINE=1` in cmd) before starting the program.

Use **Windows Terminal** (not the old `cmd` window) so Armenian letters display correctly.

## Audio setup

Nothing extra to install. Windows can record any output device in *loopback* mode (WASAPI), which captures
exactly what the call sounds like, while I keep hearing it normally.

```
python -m hylive --list-devices
```
Example output (indices and names will differ on your machine):
```
WASAPI input devices (use the index with --mic / --system):

   idx  kind      ch   rate  name
    14  mic        2  48000  Microphone Array (Realtek)   <- default --mic
    17  loopback   2  48000  Headphones (WH-1000XM4) [Loopback]   <- default --system
```

- `--system` must be the **loopback** of the device the call app plays through. By default this is the loopback
  of the Windows default output. If the call app (Zoom/Meet/Teams) plays to a different device, pick that
  device's `[Loopback]` index.
- `--mic` is the microphone. The call app and this program can use it at the same time (WASAPI shared mode).
- Use **headphones**. Otherwise the mic also picks up the other side's voices, which then show up as `Me`
  (echo handling is out of scope).

## Run

```
python -m hylive                         # default mic + default loopback
python -m hylive --mic 14 --system 17    # explicit devices
```
Stop with Ctrl+C. Startup (model loading + warm-up) can take a minute. The program prints the GPU, the models
and the GPU memory used, then `Listening.`

**Test without a call:** replay recordings through the exact same pipeline (in real time, so the latency
numbers stay meaningful):
```
python -m hylive --replay-system call_side.wav --replay-mic my_side.wav
```

Useful flags: `--asr-model`, `--asr-language hy` (for multilingual Whisper checkpoints), `--mt-model`,
`--spk-threshold`, `--min-silence-mic`, `--min-silence-system`, `--max-segment`, `--no-split`,
`--split-threshold`. See `python -m hylive --help`.

**Record a test clip** (same capture code, saved as 16 kHz WAV in `data/`, which git ignores):
```
python scripts/record.py --system default --seconds 180 --out data\interview.wav
```

## Models

Armenian is low-resource, so stock models are weak. The choices below are logged with reasons in `DECISIONS.md`.

### ASR: `BuzzASR/armenian` (default)
A full fine-tune of `openai/whisper-large-v3` with an Armenian-specific tokenizer (BuzzASR, EMNLP 2026 Findings).

| Model | Reported (normalized) | Source |
| --- | --- | --- |
| **BuzzASR/armenian** | FLEURS CER 3.7 / WER 11.9; FLEURS + Common Voice 25 CER 2.3 / WER 7.5 | model card |
| openai/whisper-large-v3 (zero-shot) | combined CER 15.5 | BuzzASR model card |
| Chillarmo/whisper-large-v3-turbo-armenian | not reported; turbo = fewer decoder layers, faster | to measure |
| small/tiny Armenian fine-tunes (e.g. Edmon02/whisper-small-hy) | WER ~75% | model card |

**Why:** it has by far the best published numbers, and they include FLEURS (not only read Common Voice
sentences). **Trade-off:** it's about 2B parameters in fp16, so it needs the most VRAM and is the slowest
candidate. Because the tokenizer is replaced, it can't simply be converted to faster-whisper. If it's too
slow or too big on my GPU, the fallback is the turbo fine-tune
(`--asr-model Chillarmo/whisper-large-v3-turbo-armenian --asr-language hy`).
**To do:** confirm with `scripts/eval.py` on my own recordings and call audio, which are not studio clips.

### Translation: `facebook/nllb-200-distilled-600M` (default)
A dedicated MT model with Armenian (`hye_Armn`) support. It's small and fast, and `--mt-model
facebook/nllb-200-distilled-1.3B` (or 3.3B) trades speed for quality. Considered: MADLAD-400 (3B+,
slower), and a local LLM (more fluent English, but weaker on Armenian and much heavier). NLLB is licensed
CC-BY-NC (non-commercial).

### Speaker identification: `speechbrain/spkrec-ecapa-voxceleb` + split at voice changes + online clustering
Call side only; the mic is always `Me`. It works in three steps:
1. **Shorter phrases.** Call-side phrases end after only 0.3 s of silence and are cut at 8 s at the latest,
   because people in a conversation hand over with short pauses.
2. **Split at voice changes** (`SpeakerSplitter`). People also hand over with *no* pause, so a phrase can still
   hold two voices. The phrase is embedded in 1.5 s windows every 0.5 s (one GPU batch, a few ms) and the
   windows are grouped into two voices. If the two groups sound different (cosine < `--split-threshold`,
   0.5), the phrase is cut where the voice switches, at the quietest spot nearby. Pieces shorter than 1.5 s
   are never cut off, and neighbouring pieces that still sound alike are merged back. Turn it off with
   `--no-split` to compare.
3. **Label each piece** (`SpeakerTracker`). It goes to the known speaker with the most similar centroid if
   cosine ≥ `--spk-threshold` (0.5), otherwise it becomes a new speaker. Pieces with less than 1 s of speech
   are matched to the closest speaker but never create one.

Considered: diart / pyannote segmentation (purpose-built streaming diarization, but gated models that need a
Hugging Face token, a heavier dependency, and more to tune). Splitting VAD phrases and clustering them online
is simpler, has no extra dependencies, and every step is unit-tested.

### VAD: Silero VAD
Small, CPU, about 1 ms per 32 ms frame, and the weights ship with the pip package.

## Architecture

```
 mic (WASAPI)        -> LiveSource -> Segmenter("mic")    --\
                                                            +--> queue --> PhraseProcessor (GPU, 1 thread)
 speakers (loopback) -> LiveSource -> Segmenter("system") --/              [split at voice change]
                                                                           ASR -> speaker -> MT -> print
```

| File | Role |
| --- | --- |
| `hylive/audio.py` | device list/selection, capture (any rate/channels → 16 kHz mono), file replay |
| `hylive/vad.py` | Silero VAD + `Segmenter`: cuts a phrase after 0.5 s (mic) / 0.3 s (call) of silence, keeps 0.2 s padding, force-cuts at 8 s |
| `hylive/asr.py` | Whisper-architecture ASR via transformers |
| `hylive/translate.py` | NLLB translation |
| `hylive/speakers.py` | ECAPA embedder, `SpeakerSplitter` (cut at voice changes), `SpeakerTracker` (online clustering) |
| `hylive/pipeline.py` | threads, queue, per-phrase processing and timing |
| `hylive/output.py` | terminal format |
| `scripts/eval.py` | WER/CER + model timing on a manifest of clips |
| `scripts/record.py` | record the mic or the call side to a WAV, for repeatable replay tests |

Each source has its own thread (capture + VAD on CPU). All model work happens in one worker thread, in phrase
order. Latency budget: about 0.5 s to detect the end of a phrase, then ASR + speaker + MT on the GPU. Every
printed line shows the actual split.

Lines print in the order their phrases **end**. The timestamp is when the phrase **started**, so a long phrase
can appear after a shorter one that started later.

## Testing

- `pytest -q`: segmenter, voice-change splitter, speaker tracker, gap-filling, output format, text
  normalisation, sentence splitting, labels. No models or devices needed. Each safeguard in the splitter
  was checked by removing it and confirming a test fails.
- `scripts/eval.py --manifest data/eval/manifest.csv`: WER/CER and timing per model (manifest = `path,text`).
- `TESTS.md`: the requirement checklist from the brief, plus manual QA cases for the live run.

## Known limitations

- **ASR/MT accuracy is not measured yet** (no eval set); the numbers above are from model cards.
- **Overlapping speech is not separated.** When two people talk *at the same time*, that piece gets one label.
- **The voice-change split handles two voices per phrase.** Turns shorter than 1.5 s (a quick "Հա") stay in
  the neighbouring piece, and the cut position is only accurate to about ±0.25 s.
- **A split shows the real delay.** The first piece of a split phrase is printed only once the whole phrase
  has ended. Its latency is measured from the end of *that piece*, so it can be several seconds higher than
  usual (up to the 8 s phrase limit, plus processing).
- **Speaker labels are order-sensitive.** If the first phrase of a new speaker is mixed or mislabelled, the next
  phrases can follow it into the wrong label (seen at the start of the interview replay). The threshold (0.5)
  is tuned on one 3-minute YouTube interview only, not on real Opus-compressed call audio.
- **Shorter call-side pauses (0.3 s) sometimes split a sentence in two**, which makes each half harder to translate.
- **Very short phrases** ("Այո") are labelled as the closest known speaker, which may be wrong.
- **Changing the default output device mid-session** (plugging in headphones) is not followed; restart the program.
- **Whisper can hallucinate** on noise. Only the VAD and the repetition guards protect against it.
- **One GPU worker:** when both sides talk at once, phrases wait in the queue (shown as `queue` in the timings).

## What I'd improve with more time

- Measure on my own recordings first, then pick ASR/MT from the numbers.
- Faster ASR: a CTranslate2/faster-whisper build of a compatible fine-tune, or int8 quantisation.
- Streaming partial results (SimulStreaming-style) for long monologues.
- Use the call-side audio to suppress echo in the mic stream.
