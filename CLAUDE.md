# Project rules (for any AI chat working on this repo)

- Goal and constraints: see `PLAN.md`. Decisions and their reasons: `DECISIONS.md`. Don't re-decide them silently;
  propose a change and log it.
- Python 3.10+, Windows + NVIDIA GPU is the target machine.
- Keep modules separate: `audio.py` / `vad.py` know nothing about models; `asr.py` / `translate.py` /
  `speakers.py` know nothing about audio devices.
- Fail loudly. No silent fallbacks (CPU fallback, default device fallback, swallowed exceptions).
- Don't add features beyond the brief. Improve the weakest measured link first.
- Verify library APIs and model names against docs before using them; cite the source.
- Never commit model weights, audio recordings or API keys.
