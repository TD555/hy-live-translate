"""Command line entry point: python -m hylive --help"""

import argparse
import sys
import time
import warnings

import numpy as np

from hylive import SAMPLE_RATE


def parse_args(argv=None):
    p = argparse.ArgumentParser(prog="python -m hylive", description="Live Armenian -> English call transcription.")
    g = p.add_argument_group("audio")
    g.add_argument("--list-devices", action="store_true", help="print audio devices and exit")
    g.add_argument("--mic", default="default", help="microphone device index, or 'default'")
    g.add_argument("--system", default="default", help="loopback device index (call audio), or 'default'")
    g.add_argument("--replay-mic", metavar="FILE", help="replay a file as the mic side instead of live capture")
    g.add_argument("--replay-system", metavar="FILE", help="replay a file as the call side instead of live capture")

    g = p.add_argument_group("models")
    g.add_argument("--device", default="cuda", choices=["cuda", "cpu"])
    g.add_argument("--asr-model", default="BuzzASR/armenian")
    g.add_argument("--asr-language", default=None,
                   help="language token for multilingual Whisper checkpoints, e.g. 'hy'. Leave unset for BuzzASR.")
    g.add_argument("--mt-model", default="facebook/nllb-200-distilled-600M")
    g.add_argument("--mt-beams", type=int, default=4)
    g.add_argument("--spk-dir", default="pretrained_models/spkrec-ecapa-voxceleb", help="where the ECAPA model is copied")

    g = p.add_argument_group("tuning")
    g.add_argument("--vad-threshold", type=float, default=0.5)
    g.add_argument("--min-silence-mic", type=float, default=0.5, help="seconds of silence that end a mic phrase")
    g.add_argument("--min-silence-system", type=float, default=0.3,
                   help="same for the call side; shorter, because speakers hand over with short pauses")
    g.add_argument("--max-segment", type=float, default=8.0, help="force-cut phrases longer than this (s)")
    g.add_argument("--spk-threshold", type=float, default=0.5, help="cosine similarity to join a known speaker")
    g.add_argument("--spk-min-new", type=float, default=1.0, help="shortest phrase (s) that may create a new speaker")
    g.add_argument("--no-split", action="store_true",
                   help="don't split call-side phrases at voice changes (for comparison)")
    g.add_argument("--split-threshold", type=float, default=0.5,
                   help="split only if the two halves' voice similarity is below this")
    g.add_argument("--no-timings", action="store_true", help="hide the latency line under each phrase")
    return p.parse_args(argv)


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def load_models(args):
    import torch

    from hylive.asr import WhisperAsr
    from hylive.speakers import EcapaEmbedder
    from hylive.translate import NllbTranslator

    if args.device == "cuda" and not torch.cuda.is_available():
        raise SystemExit(
            "CUDA is not available to PyTorch. Install the CUDA build of torch (see README), "
            "or pass --device cpu explicitly (much slower, will not meet 5 s)."
        )
    dtype = torch.float16 if args.device == "cuda" else torch.float32
    if args.device == "cuda":
        log(f"GPU: {torch.cuda.get_device_name(0)}")

    t = time.monotonic()
    asr = WhisperAsr(args.asr_model, args.device, dtype, language=args.asr_language)
    log(f"ASR  {args.asr_model} loaded in {time.monotonic() - t:.1f}s")
    t = time.monotonic()
    mt = NllbTranslator(args.mt_model, args.device, dtype, num_beams=args.mt_beams)
    log(f"MT   {args.mt_model} loaded in {time.monotonic() - t:.1f}s")
    t = time.monotonic()
    emb = EcapaEmbedder(args.device, args.spk_dir)
    log(f"SPK  {EcapaEmbedder.SOURCE} loaded in {time.monotonic() - t:.1f}s")

    # Loading warnings (missing weights etc.) matter and were shown above. From here on, transformers
    # only repeats harmless generate() notices on every phrase, which bury the output; keep errors only.
    import transformers

    transformers.logging.set_verbosity_error()

    # Warm-up: the first CUDA call of each model is slow; do it now, not on the first real phrase.
    t = time.monotonic()
    one_second = np.zeros(SAMPLE_RATE, np.float32)
    asr.transcribe(one_second)
    mt.translate("Բարև")
    emb.embed(one_second)
    emb.embed_batch([np.zeros(int(1.5 * SAMPLE_RATE), np.float32)] * 12)  # the splitter's window batch
    log(f"warm-up done in {time.monotonic() - t:.1f}s")
    if args.device == "cuda":
        log(f"GPU memory in use: {torch.cuda.memory_allocated() / 2**30:.1f} GiB")
    return asr, mt, emb


def open_sources(args) -> dict:
    from hylive.audio import FileSource, LiveSource, resolve_device

    if args.replay_mic or args.replay_system:
        sources = {}
        if args.replay_mic:
            sources["mic"] = FileSource(args.replay_mic)
        if args.replay_system:
            sources["system"] = FileSource(args.replay_system)
        return sources
    return {
        "mic": LiveSource(resolve_device("mic", args.mic)),
        "system": LiveSource(resolve_device("system", args.system)),
    }


def main(argv=None) -> None:
    args = parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # Armenian script on the Windows console

    if args.list_devices:
        from hylive.audio import list_devices

        list_devices()
        return

    from hylive.output import Printer
    from hylive.pipeline import PhraseProcessor, run
    from hylive.speakers import SpeakerSplitter, SpeakerTracker
    from hylive.vad import Segmenter, SileroVad

    asr, mt, emb = load_models(args)
    # Silero VAD is a TorchScript model; torch warns that torch.jit.load is deprecated. Harmless.
    warnings.filterwarnings("ignore", message=r".*torch\.jit\.load.*deprecated", category=FutureWarning)
    sources = open_sources(args)
    segmenters = {
        name: Segmenter(
            name,
            SileroVad(),  # one per source: the VAD keeps internal state
            threshold=args.vad_threshold,
            min_silence_s=args.min_silence_mic if name == "mic" else args.min_silence_system,
            max_segment_s=args.max_segment,
        )
        for name in sources
    }
    for name, src in sources.items():
        log(f"{name:>6}: {src.name}")
    log("Listening. Ctrl+C to stop.\n")

    splitter = None if args.no_split else SpeakerSplitter(emb, threshold=args.split_threshold)
    log(f"voice-change split: {'off' if splitter is None else f'on (threshold {args.split_threshold})'}")
    processor = PhraseProcessor(
        asr, mt, emb,
        SpeakerTracker(threshold=args.spk_threshold, min_new_s=args.spk_min_new),
        Printer(show_timings=not args.no_timings),
        session_start=time.monotonic(),
        splitter=splitter,
    )
    run(sources, segmenters, processor)


if __name__ == "__main__":
    main()
