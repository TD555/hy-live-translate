"""D8: WASAPI loopback stops sending packets when nothing plays. The last phrase must still come out."""

import queue
import threading
import time

import numpy as np

from hylive.pipeline import _source_loop
from hylive.types import AudioChunk
from hylive.vad import Segmenter
from tests.test_segmenter import fake_vad


class LoopbackThatGoesQuiet:
    """Delivers 1 s of 'speech' in 50 ms blocks, then nothing at all (like loopback with no audio playing)."""

    name, done = "fake loopback", False

    def __init__(self):
        self.blocks = [np.full(800, 0.3, np.float32) for _ in range(20)]

    def read(self, timeout):
        if self.blocks:
            return AudioChunk(self.blocks.pop(0), time.monotonic())
        time.sleep(timeout)
        return None

    def close(self):
        pass


def test_last_phrase_is_emitted_even_when_source_stops_sending():
    q, stop = queue.Queue(), threading.Event()
    seg = Segmenter("system", fake_vad, min_silence_s=0.5)
    t = threading.Thread(target=_source_loop, args=(LoopbackThatGoesQuiet(), seg, q, stop), daemon=True)
    t.start()
    try:
        kind, segment, emitted_at = q.get(timeout=2.0)  # without gap-filling this would time out
    finally:
        stop.set()
    assert kind == "segment"
    assert segment.duration >= 1.0
    assert emitted_at - segment.end_time < 1.0  # 0.5 s of silence + at most one 0.25 s gap step
