"""Wiring: one thread per audio source (capture + VAD) -> one queue -> one GPU worker.

    mic source    --> Segmenter("mic")    --\
                                             +--> queue --> PhraseProcessor --> terminal
    system source --> Segmenter("system") --/              (ASR, speaker, MT)
"""

import queue
import sys
import threading
import time

import numpy as np

from hylive import SAMPLE_RATE
from hylive.types import AudioChunk, Segment

GAP_S = 0.25  # if a source sends nothing for this long, feed this much silence (DECISIONS D8)


class PhraseProcessor:
    """Takes one Segment and prints its line. All model work happens here, in one thread."""

    def __init__(self, asr, translator, embedder, tracker, printer, session_start: float):
        self.asr, self.translator = asr, translator
        self.embedder, self.tracker = embedder, tracker
        self.printer = printer
        self.session_start = session_start

    def speaker_of(self, seg: Segment) -> tuple[str, str]:
        """(label, debug note). Everything from the mic is 'Me'."""
        if seg.source == "mic":
            return "Me", ""
        # speech_duration, not duration: the 0.4 s of padding made one-word phrases look long enough
        # to create a new speaker (phantom Speaker 3/4 in the 2026-10-30 interview replay).
        n, sim = self.tracker.assign(self.embedder.embed(seg.audio), seg.speech_duration)
        return f"Speaker {n}", f"sim {sim:.2f}"

    def process(self, seg: Segment, emitted_at: float) -> None:
        t0 = time.monotonic()
        hy = self.asr.transcribe(seg.audio)
        t1 = time.monotonic()
        if not hy:
            print(f"[skip] {seg.source} phrase of {seg.duration:.1f}s: ASR returned no text", file=sys.stderr)
            return
        speaker, note = self.speaker_of(seg)
        t2 = time.monotonic()
        en = self.translator.translate(hy)
        t3 = time.monotonic()
        timings = {
            "vad": emitted_at - seg.end_time,  # silence needed to detect the end of the phrase
            "queue": t0 - emitted_at,
            "asr": t1 - t0,
            "spk": t2 - t1,
            "mt": t3 - t2,
            "total": t3 - seg.end_time,
        }
        self.printer.show(seg.start_time - self.session_start, speaker, hy, en, timings, note)


def _source_loop(src, segmenter, out: queue.Queue, stop: threading.Event) -> None:
    try:
        while not stop.is_set():
            chunk = src.read(timeout=GAP_S)
            if chunk is None:
                if src.done:
                    break
                chunk = AudioChunk(np.zeros(int(GAP_S * SAMPLE_RATE), np.float32), time.monotonic())
            for seg in segmenter.push(chunk):
                out.put(("segment", seg, time.monotonic()))
    except BaseException as e:  # hand the error to the main thread so the program stops loudly
        out.put(("error", e, None))
    finally:
        out.put(("done", segmenter.source, None))


def run(sources: dict, segmenters: dict, processor: PhraseProcessor) -> None:
    """sources / segmenters: {"mic": ..., "system": ...}. Runs until all sources end or Ctrl+C."""
    q: queue.Queue = queue.Queue()
    stop = threading.Event()
    threads = []
    for name, src in sources.items():
        t = threading.Thread(
            target=_source_loop, args=(src, segmenters[name], q, stop), name=f"src-{name}", daemon=True
        )
        t.start()
        threads.append(t)

    active = len(sources)
    try:
        while active:
            try:
                kind, payload, emitted_at = q.get(timeout=0.5)  # timeout keeps Ctrl+C responsive on Windows
            except queue.Empty:
                continue
            if kind == "error":
                raise payload
            if kind == "done":
                active -= 1
                continue
            processor.process(payload, emitted_at)
    except KeyboardInterrupt:
        print("\nStopping.")
    finally:
        stop.set()
        for t in threads:  # let the source threads exit before their audio objects are freed
            t.join(timeout=2 * GAP_S + 0.5)
        for src in sources.values():
            src.close()
