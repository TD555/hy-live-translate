# TESTS

These checks come from the brief's requirements. Run them before the interview.
`[auto]` means it's covered by `pytest` or `scripts/eval.py`; `[manual]` means it's run by hand with real audio.

## Requirements → checks

| # | Requirement (brief) | Check | How |
| --- | --- | --- | --- |
| R1 | Capture mic and system audio at the same time | Play an Armenian video and speak over it; both `Me` and `Speaker N` lines appear | [manual] |
| R2 | User picks input devices | `--list-devices` shows mic and loopback devices; `--mic N --system M` uses them; a wrong index stops with a clear error | [manual] |
| R3 | Armenian transcription | WER/CER on the eval set, reported per model | [auto] `scripts/eval.py` |
| R4 | English translation | Read the EN lines for the eval set: is the meaning understandable? Note the bad ones | [manual] on `eval.py` output |
| R5 | Mic is always `Me` | Unit test + live check | [auto] `test_pipeline_labels` + [manual] |
| R6 | Different call-side people get different labels | Recording with 2–3 known voices → number of labels = number of voices | [auto] `test_speakers.py` (synthetic) + [manual] |
| R7 | Same person keeps the same label | A speaks, B speaks, A speaks again → A gets its first label back | [auto] `test_speakers.py` + [manual] |
| R8 | Output shows time, speaker, HY, EN | Format test | [auto] `test_output.py` |
| R9 | ≤ 5 s from end of phrase to EN line | Every line prints latency; check the **max** over a 5-minute call, not the average | [manual] live + replay |
| R10 | Local only | After the first download, run with `HF_HUB_OFFLINE=1` and Wi-Fi off; it still works | [manual] |

## Edge cases / QA questions

- [ ] Silence for 30 s: nothing is printed (no hallucinated lines).
- [ ] Background music or keyboard noise only: no lines, or very few.
- [ ] A monologue longer than 12 s gets split into several lines and no words go missing at the cut.
- [ ] Nothing playing on the speakers after the last phrase: that phrase still prints within 5 s (D8).
- [ ] Both sides talk at the same time: both appear; how high does latency go?
- [ ] One-word answers ("Այո", "Չէ"): what label do they get?
- [ ] Phrases with English words / names mixed in (code-switching).
- [ ] Two call-side voices of the same gender: are they still kept apart?
- [ ] The Armenian script displays correctly in Windows Terminal.
- [ ] Ctrl+C stops the program cleanly.
- [ ] First phrase after startup isn't slow (models warmed up).
- [ ] The default output device changes (headphones plugged in) mid-session: what happens? (Expected: loopback
      keeps recording the old device — a known limitation.)

## Unit tests

```
pytest -q
```
They run without models or audio devices: the segmenter uses a fake VAD, and the speaker tracker uses synthetic embeddings.
