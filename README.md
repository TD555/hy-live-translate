# hy-live-translate

Listens to a live call and prints each spoken Armenian phrase with an English translation, labelled by
speaker (`Me` for my microphone, `Speaker 1`, `Speaker 2`, … for the other side). Everything runs locally
on a Windows laptop with an NVIDIA GPU.

Real output from a replay of a recorded two-person interview:
```
[00:01:23] Speaker 2
  HY: Հայկական շոու բիզնեսում բայց կուզեր որ այդ երգը հենց քոնը լիներ
  EN: In Armenian show business, but I'd like that song to be yours.
  (latency 1.86s = vad 0.33 + queue 0.00 + asr 1.14 + spk 0.02 + mt 0.38 | sim 0.80)
```

The last line shows the time from the **end of the phrase** to the printed English line, split by stage.
`sim` is the voice similarity used to choose the speaker label. Hide this line with `--no-timings`.

## Status (2026-11-01)

Measured on my laptop (RTX 4060 Laptop GPU, 8 GB; all three models together use 4.1 GiB):

| Test | Result |
| --- | --- |
| Replay of `interview.wav` (180 s YouTube interview, 2 people, fast casual speech), final settings | 35 lines, latency **0.81–2.78 s**, exactly **2** call-side labels |
| Live, 3 min (same interview through the speakers + me talking), early settings | 33/34 lines under 5 s; mic → `Me` always correct; the one outlier (7.0 s) was an NLLB repetition loop, fixed since |
| My own voice, laptop mic: 5 read sentences, recorded and replayed | 5/5 recognised; word error rate about **21%** (5 of 24 words); English correct for 4 of 5; latency 1.5–1.6 s |
| Offline: Wi-Fi off, `HF_HUB_OFFLINE=1` | starts and runs normally; Ctrl+C exits cleanly |
| Unit tests (`pytest -q`) | 22 passed |

Not measured yet:
- **ASR/MT accuracy on a proper eval set (WER/CER).** `scripts/eval.py` exists, but the only measurement so far
  is the 5-sentence test above, which is far too small to be reliable. The accuracy numbers under *Models* come
  from model cards. Fast casual speech with slang and names has many more errors (see *Known limitations*).
- **Speaker-label accuracy per phrase.** Two labels appear, as expected, but I have not counted correct vs wrong
  labels against a hand-made ground truth. From the content, most phrases look right; some hold both voices.
- **A real call** (Zoom/Meet, Opus-compressed audio, ≥ 2 remote people). All call-side tests so far used a
  YouTube recording.

## Setup (Windows 10/11, NVIDIA GPU)

1. **Python 3.10–3.13** in a fresh virtual environment:
   ```
   python -m venv .venv
   .venv\Scripts\activate
   ```
   Every new terminal needs `.venv\Scripts\activate` first; the prompt must start with `(.venv)`. Without it,
   `python`/`pytest` may come from another installation (e.g. Anaconda) that lacks the packages.
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
4. **First run downloads the models** from Hugging Face (about 6–7 GB in total, no account or token needed).
   Let the first run finish completely: a download running in the background made my first timings 3× slower.
   After that, set `$env:HF_HUB_OFFLINE=1` (PowerShell) so the program uses only the local copies.

Use **Windows Terminal** (not the old `cmd` window) so Armenian letters display correctly.

**Before a live session:** laptop plugged in, Windows power mode *Best performance*, other GPU-heavy apps
(browser video) closed. In one replay all three models suddenly ran 3–5× slower from about two minutes in, and
the latency grew to 16 s. I could not reproduce it under these conditions, and the cause is not confirmed
(see `DECISIONS.md`).

## Audio setup

Nothing extra to install. Windows can record any output device in *loopback* mode (WASAPI), which captures
exactly what the call sounds like, while I keep hearing it normally.

```
python -m hylive --list-devices
```
Output on my laptop:
```
   idx  kind      ch   rate  name
    12  mic        2  48000  Microphone Array (Intel® Smart Sound Technology for Digital Microphones)   <- default --mic
    13  loopback   2  48000  Speakers (Realtek(R) Audio) [Loopback]   <- default --system
    14  loopback   2  48000  FxSound Speakers (FxSound Audio Enhancer) [Loopback]
```

- `--system` must be the **loopback** of the device the call app plays through. By default it is the loopback
  of the Windows default output. If the call app plays to a different device (e.g. FxSound, or headphones), pick
  that device's `[Loopback]` index.
- `--mic` is the microphone. The call app and this program can use it at the same time (WASAPI shared mode).
- Use **wired headphones**. Otherwise the mic also picks up the other side, which then shows up as `Me` (echo
  handling is out of scope). Bluetooth headsets switch to a low-quality call mode and add new devices.
- Plug the headphones in **before** starting, then run `--list-devices` again: indices can change.

## Run

```
python -m hylive                         # default mic + default loopback
python -m hylive --mic 12 --system 13    # explicit devices
```
Stop with Ctrl+C. Startup (model loading + warm-up) takes about one minute. The program prints the GPU, the
models and the GPU memory used, then `Listening.`

**Test without a call:** replay recordings through the exact same pipeline, in real time, so the latency
numbers stay meaningful. With a `--replay-*` flag, no live device is opened.
```
python -m hylive --replay-system data\interview.wav
python -m hylive --replay-system call_side.wav --replay-mic my_side.wav
```

**Record a test clip** (same capture code, 16 kHz WAV in `data/`, which git ignores). Start the command, then
press play:
```
python scripts/record.py --system default --seconds 180 --out data\interview.wav
```

Useful flags: `--asr-model`, `--asr-language hy` (for multilingual Whisper checkpoints), `--mt-model`,
`--spk-threshold`, `--min-silence-mic`, `--min-silence-system`, `--max-segment`. See `python -m hylive --help`.

## Models

Armenian is low-resource, so stock models are weak. Every choice is logged with reasons in `DECISIONS.md`.

### ASR: `BuzzASR/armenian` (default)
A full fine-tune of `openai/whisper-large-v3` with an Armenian-specific tokenizer (BuzzASR, EMNLP 2026 Findings).

| Model | Reported (normalized) | Source |
| --- | --- | --- |
| **BuzzASR/armenian** | FLEURS CER 3.7 / WER 11.9; FLEURS + Common Voice 25 CER 2.3 / WER 7.5 | model card |
| openai/whisper-large-v3 (zero-shot) | combined CER 15.5 | BuzzASR model card |
| Chillarmo/whisper-large-v3-turbo-armenian | not reported; turbo = fewer decoder layers, faster | not measured |
| small/tiny Armenian fine-tunes (e.g. Edmon02/whisper-small-hy) | WER ~75% | model card |

**Why:** by far the best published numbers, and they include FLEURS (not only read Common Voice sentences).
**Trade-off:** about 2B parameters in fp16, the slowest candidate, and the replaced tokenizer means it can't
simply be converted to faster-whisper. **Measured speed:** 0.4–0.9 s for a 1–3 s phrase, up to 2.2 s for an
8 s phrase, so speed is not a reason to switch. The turbo fine-tune stays the fallback
(`--asr-model Chillarmo/whisper-large-v3-turbo-armenian --asr-language hy`).

### Translation: `facebook/nllb-200-distilled-600M` (default)
A dedicated MT model with Armenian (`hye_Armn`) support; 0.1–0.8 s per phrase. Considered: the 1.3B/3.3B
versions (better, slower; switch with `--mt-model`), MADLAD-400 (3B+, slower) and a local LLM (more fluent
English, but weaker on Armenian and much heavier). Licence CC-BY-NC (non-commercial).
On long multi-sentence input the 600M model looped once ("I'm in rap, I'm in rap…") and dropped content, so the
text is split into sentences, translated as one batch, with repeated 4-grams blocked and the output length capped.

### Speaker identification: `speechbrain/spkrec-ecapa-voxceleb` + online clustering
One 192-dim voice embedding per call-side phrase (~0.02 s). The phrase goes to the known speaker with the most
similar centroid if cosine similarity ≥ `--spk-threshold` (0.5), otherwise it becomes a new speaker. Phrases
with less than 1 s of speech can't create a speaker; they go to the closest one.

How the settings were found, on the same recorded interview each time:

| Attempt | Result |
| --- | --- |
| Phrases cut after 0.5 s of silence, max 12 s | every call-side line `Speaker 1`: people hand over with shorter pauses, so most phrases held both voices |
| Call side cut after 0.3 s, max 8 s, threshold 0.5 | host and guest separated most of the time; latency also dropped; phantom Speakers 3/4 on one-word phrases |
| Bug fix: length check used padded length instead of speech length | exactly 2 labels |
| Split phrases at voice changes (1.5 s windows) | **rejected:** 7 labels instead of 2 and first-piece latency up to 7.4 s. Kept in git history (commit + revert), see D9 in `DECISIONS.md` |

Considered: diart / pyannote segmentation (purpose-built for speaker changes and overlap, but gated models with
an HF token, heavier, and more to tune in the time available).

### VAD: Silero VAD
Small, CPU, about 1 ms per 32 ms frame, and the weights ship with the pip package.

## Architecture

```
 mic (WASAPI)        -> LiveSource -> Segmenter("mic")    --\
                                                            +--> queue --> PhraseProcessor (GPU, 1 thread)
 speakers (loopback) -> LiveSource -> Segmenter("system") --/              ASR -> speaker -> MT -> print
```

| File | Role |
| --- | --- |
| `hylive/__main__.py` | command line: device list, model loading and warm-up, starting the sources |
| `hylive/types.py` | `AudioChunk` and `Segment` data types passed between the parts |
| `hylive/audio.py` | device list/selection, capture (any rate/channels → 16 kHz mono), file replay |
| `hylive/vad.py` | Silero VAD + `Segmenter`: cuts a phrase after 0.5 s (mic) / 0.3 s (call) of silence, keeps 0.2 s padding, force-cuts at 8 s |
| `hylive/asr.py` | Whisper-architecture ASR via transformers |
| `hylive/translate.py` | sentence split + NLLB translation |
| `hylive/speakers.py` | ECAPA embedder + `SpeakerTracker` (online clustering) |
| `hylive/pipeline.py` | threads, queue, silence fill for a quiet loopback, per-phrase processing and timing |
| `hylive/output.py` | terminal format |
| `hylive/textnorm.py` | Armenian text normalisation for WER/CER |
| `scripts/eval.py` | WER/CER + model timing on a manifest of clips |
| `scripts/record.py` | record a mic or loopback clip for replay tests |

Each source has its own thread (capture + VAD on CPU). All model work happens in one worker thread, in phrase
order. WASAPI loopback sends no data while nothing plays, so the source thread feeds silence after 0.25 s without
packets; otherwise the last phrase would wait until someone speaks again.

Lines print in the order their phrases **end**. The timestamp is when the phrase **started**, so a long phrase
can appear after a shorter one that started later.

## Working method

- `PLAN.md`: the plan before coding.
- `DECISIONS.md`: each decision with its reason, alternatives and measured evidence, including rejected ones.
- `TESTS.md`: requirement checklist from the brief + manual QA cases.
- `CLAUDE.md`: rules for the AI assistant (keep it simple, fail loudly, verify APIs).
- Every change was compared on the **same recording** (`--replay-system data\interview.wav`) using the per-stage
  timings, rather than judged by impression.
- **Fail loudly:** no CPU fallback (`--device cpu` must be explicit), a wrong device index stops with the list,
  a model load failure raises, an empty transcript is reported on stderr.
- `chats/`: every Claude session for this project, exported in full, one Markdown file per session.

## Testing

- `pytest -q` (22 tests): segmenter, speaker tracker, silence fill, pipeline labels, output format, sentence
  split, text normalisation. No models or devices needed.
- `scripts/eval.py --manifest data/eval/manifest.csv`: WER/CER and timing per model (manifest = `path,text`).
  Not run yet (no eval set).

## Known limitations

- **ASR on less common words and names.** Even in clear read speech, rare words turn into similar-sounding ones:
  `ծրագրավորող Երևանում` (programmer in Yerevan) → `գործարարող երևում`. In fast, casual speech it gets worse:
  `քավր` (cover) → `հավր`, the name Վարդան → `վարդնջան`, and names of people come out garbled.
- **MT (NLLB-600M) is literal and weak on names and interjections.** Վարդան → "the rose" / "the verb";
  `բա` → "What are you talking about?". Each phrase is translated on its own, without the previous context.
- **One label per phrase.** When both people speak inside one phrase (quick back-and-forth or overlap), it gets one
  label; the Armenian text then often contains dialogue dashes `- … - …`. Splitting at voice changes was tried
  and rejected (see *Speaker identification*).
- **Speaker labels are order-sensitive.** If the first phrase of a new speaker is mixed, the following phrases
  can follow it to the wrong label (seen at 00:29 in the interview replay). Very short phrases (`Այո`) go to the
  closest speaker, which may be wrong. Settings are tuned on one 3-minute recording, not on real call audio.
- **0.3 s call-side pauses sometimes split a sentence in two**, which makes each half harder to translate.
- **GPU slowdowns** (see *Setup*): with one worker, a slow GPU makes the queue grow, and the latency grows with it.
- **Changing the output device mid-session** (plugging in headphones) is not followed; restart the program.
- **Non-speech voice sounds** (clearing the throat, "hmm") pass the VAD and print as a line, and NLLB may invent a
  meaning for them: `Հըհ հըհ` → "Oh, my God.". A minute of silence, typing and mouse noise printed nothing.
- **Whisper can hallucinate** on noise. Only the VAD and the repetition guards protect against it.

## What I'd improve with more time

1. Build an eval set (my recordings + FLEURS `hy_am`) and run `scripts/eval.py`: real WER/CER, then compare
   the turbo ASR model and NLLB-1.3B by numbers. There is about 2 s of latency headroom for a bigger MT model.
2. A time-based speaker ground truth for the test recording, to count label accuracy across setting changes.
3. A purpose-built speaker-change / overlap model (pyannote segmentation) for the mixed phrases.
4. Pass the previous sentence as context to MT; a small name list for ASR/MT.
5. Faster ASR (int8, or a CTranslate2 build of a compatible fine-tune) and streaming partial results for long
   monologues.