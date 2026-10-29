"""Measure ASR accuracy and model speed on a set of Armenian clips with known text.

    python scripts/eval.py --manifest data/eval/manifest.csv
    python scripts/eval.py --manifest data/eval/manifest.csv --asr-model Chillarmo/whisper-large-v3-turbo-armenian --asr-language hy

manifest.csv has the columns `path,text`. Paths are relative to the manifest file, and any format soundfile
can read works (wav, flac, ogg). Prints WER/CER and timing, and writes one row per clip to --out so the
English translations can be read and judged by hand.
"""

import argparse
import csv
import statistics
import sys
import time
from pathlib import Path

import jiwer
import numpy as np
import soundfile as sf
import soxr

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from hylive import SAMPLE_RATE  # noqa: E402
from hylive.textnorm import normalize_hy  # noqa: E402


def load_clip(path: Path) -> np.ndarray:
    audio, sr = sf.read(path, dtype="float32", always_2d=True)
    return soxr.resample(audio.mean(axis=1), sr, SAMPLE_RATE).astype(np.float32)


def p95(xs):
    return sorted(xs)[max(0, int(round(0.95 * len(xs))) - 1)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--asr-model", default="BuzzASR/armenian")
    ap.add_argument("--asr-language", default=None)
    ap.add_argument("--mt-model", default="facebook/nllb-200-distilled-600M")
    ap.add_argument("--no-mt", action="store_true", help="skip translation (ASR comparison only)")
    ap.add_argument("--device", default="cuda", choices=["cuda", "cpu"])
    ap.add_argument("--out", default=None, help="per-clip CSV (default: results/<model>.csv)")
    args = ap.parse_args()

    import torch

    from hylive.asr import WhisperAsr
    from hylive.translate import NllbTranslator

    if args.device == "cuda" and not torch.cuda.is_available():
        raise SystemExit("CUDA not available; pass --device cpu explicitly.")
    dtype = torch.float16 if args.device == "cuda" else torch.float32

    manifest = Path(args.manifest)
    with open(manifest, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise SystemExit(f"{manifest} has no rows")

    asr = WhisperAsr(args.asr_model, args.device, dtype, language=args.asr_language)
    mt = None if args.no_mt else NllbTranslator(args.mt_model, args.device, dtype)
    asr.transcribe(np.zeros(SAMPLE_RATE, np.float32))  # warm-up

    results, refs, hyps = [], [], []
    for row in rows:
        audio = load_clip(manifest.parent / row["path"])
        t0 = time.monotonic()
        hyp = asr.transcribe(audio)
        t1 = time.monotonic()
        en = mt.translate(hyp) if (mt and hyp) else ""
        t2 = time.monotonic()
        ref_n, hyp_n = normalize_hy(row["text"]), normalize_hy(hyp)
        refs.append(ref_n)
        hyps.append(hyp_n)
        clip_wer = jiwer.wer(ref_n, hyp_n) if ref_n else float("nan")
        results.append(dict(path=row["path"], dur=len(audio) / SAMPLE_RATE, asr_s=t1 - t0, mt_s=t2 - t1,
                            wer=clip_wer, ref=row["text"], hyp=hyp, en=en))
        print(f"{clip_wer:6.2f}  {row['path']}\n        REF {row['text']}\n        HYP {hyp}\n        EN  {en}")

    asr_times = [r["asr_s"] for r in results]
    audio_s = sum(r["dur"] for r in results)
    print("\n=== summary ===")
    print(f"model      {args.asr_model}")
    print(f"clips      {len(results)}  ({audio_s / 60:.1f} min of audio)")
    print(f"WER        {jiwer.wer(refs, hyps) * 100:.1f} %")
    print(f"CER        {jiwer.cer(refs, hyps) * 100:.1f} %")
    print(f"ASR time   mean {statistics.mean(asr_times):.2f}s  p95 {p95(asr_times):.2f}s  max {max(asr_times):.2f}s")
    print(f"ASR RTF    {sum(asr_times) / audio_s:.3f}  (seconds of compute per second of audio)")
    if mt:
        mt_times = [r["mt_s"] for r in results]
        print(f"MT time    mean {statistics.mean(mt_times):.2f}s  p95 {p95(mt_times):.2f}s  max {max(mt_times):.2f}s")

    out = Path(args.out or f"results/{args.asr_model.replace('/', '__')}.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(results[0]))
        w.writeheader()
        w.writerows(results)
    print(f"per-clip results -> {out}")


if __name__ == "__main__":
    main()
