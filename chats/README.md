# Chat sessions

| File | Dates | What it covers |
| --- | --- | --- |
| `01-2026-10-22-project-kickoff.md` | 2026-10-22 → 2026-10-30 | Research and model choice, plan, walking skeleton, patches 1–3 (warnings and device selection, MT loop fix and record script, call-side VAD/speaker defaults), live test and interview replay, handover document, voice-change split patch |
| `02-2026-10-30-continuation.md` | 2026-10-30 → 2026-11-01 | Continued from the handover: voice-change split measured and reverted (D9), GPU slowdown check, git cleanup and GitHub push, README, mic accuracy test, offline and silence checks, Zoom call test, chat export |

- `01` comes from the Claude data export (claude.ai → Settings → Privacy → Export data), converted to Markdown by
  `scripts/export_chats.py`. `readable/01-2026-10-22-project-kickoff.md` is the same session with only the
  messages, without tool calls and tool output (`scripts/readable_chat.py`).
- `02` is not part of the data export; it is copied from the session's claude.ai share page, which shows the
  messages without tool calls.