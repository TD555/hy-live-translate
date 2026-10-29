"""Terminal output."""

import sys


def clock(seconds: float) -> str:
    s = max(0, int(seconds))
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def format_block(
    elapsed_s: float, speaker: str, hy: str, en: str, timings: dict | None = None, note: str = ""
) -> str:
    """timings: stage name -> seconds, must include 'total' (end of phrase -> printed)."""
    lines = [f"[{clock(elapsed_s)}] {speaker}", f"  HY: {hy}", f"  EN: {en}"]
    if timings is not None:
        parts = " + ".join(f"{k} {v:.2f}" for k, v in timings.items() if k != "total")
        lines.append(f"  (latency {timings['total']:.2f}s = {parts}{' | ' + note if note else ''})")
    return "\n".join(lines) + "\n"


class Printer:
    def __init__(self, show_timings: bool = True, stream=None):
        self.show_timings = show_timings
        self.stream = stream or sys.stdout

    def show(self, elapsed_s: float, speaker: str, hy: str, en: str, timings: dict, note: str = "") -> None:
        block = format_block(elapsed_s, speaker, hy, en, timings if self.show_timings else None, note)
        self.stream.write(block + "\n")
        self.stream.flush()
