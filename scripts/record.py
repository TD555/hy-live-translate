"""Record one audio source to a 16 kHz mono WAV, for repeatable tests with --replay-*.

    python scripts/record.py --system default --seconds 180 --out data\\interview.wav
    python scripts/record.py --mic default --seconds 60 --out data\\me.wav

Uses exactly the same capture code as the live program. Recordings go in data/, which git ignores.
"""

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from hylive import SAMPLE_RATE  # noqa: E402
from hylive.audio import LiveSource, resolve_device  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--mic", help="microphone index or 'default'")
    src.add_argument("--system", help="loopback index or 'default'")
    ap.add_argument("--seconds", type=float, required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    kind, arg = ("mic", args.mic) if args.mic else ("system", args.system)
    source = LiveSource(resolve_device(kind, arg))
    print(f"Recording {args.seconds:.0f}s from: {source.name}  (Ctrl+C stops early)")
    chunks, t0 = [], time.monotonic()
    try:
        while time.monotonic() - t0 < args.seconds:
            chunk = source.read(timeout=0.25)
            if chunk is None:  # loopback sends nothing while nothing plays: keep the timeline with silence
                chunks.append(np.zeros(int(0.25 * SAMPLE_RATE), np.float32))
            else:
                chunks.append(chunk.samples)
    except KeyboardInterrupt:
        pass
    finally:
        source.close()
    audio = np.concatenate(chunks)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    sf.write(args.out, audio, SAMPLE_RATE)
    print(f"Saved {len(audio) / SAMPLE_RATE:.1f}s -> {args.out}")


if __name__ == "__main__":
    main()
