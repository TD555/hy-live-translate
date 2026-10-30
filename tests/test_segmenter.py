"""Segmenter logic with a fake VAD (speech = loud frame). No models needed."""

import numpy as np
import pytest

from hylive import SAMPLE_RATE
from hylive.types import AudioChunk
from hylive.vad import FRAME_S, Segmenter


def fake_vad(frame):
    return 1.0 if np.sqrt(np.mean(frame**2)) > 0.05 else 0.0


def signal(*parts):
    """parts: (seconds, is_speech) -> audio array"""
    out = []
    for sec, speech in parts:
        n = int(sec * SAMPLE_RATE)
        out.append(np.full(n, 0.3 if speech else 0.0, np.float32))
    return np.concatenate(out)


def run(audio, seg, block_s=0.05, t0=100.0):
    """Push audio in blocks; the clock says each block ends when its last sample was 'captured'."""
    block = int(block_s * SAMPLE_RATE)
    out = []
    for start in range(0, len(audio), block):
        chunk = audio[start : start + block]
        end_time = t0 + (start + len(chunk)) / SAMPLE_RATE
        out += seg.push(AudioChunk(chunk, end_time))
    return out


def test_two_phrases_are_cut_at_silence():
    audio = signal((1, False), (1.5, True), (1, False), (0.8, True), (1, False))
    segs = run(audio, Segmenter("mic", fake_vad, min_silence_s=0.5, pad_s=0.2))
    assert len(segs) == 2
    # speech ended at t0 + 2.5 s and t0 + 4.3 s; latency is measured from there
    assert segs[0].end_time == pytest.approx(102.5, abs=FRAME_S)
    assert segs[1].end_time == pytest.approx(104.3, abs=FRAME_S)
    assert segs[0].start_time == pytest.approx(101.0, abs=FRAME_S)
    # audio = speech + about 0.2 s padding on each side
    assert segs[0].duration == pytest.approx(1.9, abs=2 * FRAME_S)
    assert all(s.source == "mic" for s in segs)


def test_phrase_is_emitted_after_min_silence_not_later():
    audio = signal((0.5, False), (1, True), (0.6, False))  # only 0.6 s of silence after the phrase
    segs = run(audio, Segmenter("system", fake_vad, min_silence_s=0.5))
    assert len(segs) == 1


def test_short_blip_is_dropped():
    audio = signal((1, False), (0.1, True), (1, False))
    assert run(audio, Segmenter("mic", fake_vad, min_speech_s=0.3)) == []


def test_silence_only_gives_nothing():
    assert run(signal((5, False)), Segmenter("mic", fake_vad)) == []


def test_long_phrase_is_force_cut_without_losing_audio():
    audio = signal((0.5, False), (30, True), (1, False))
    segs = run(audio, Segmenter("mic", fake_vad, max_segment_s=12, pad_s=0.2))
    assert len(segs) == 3
    assert all(s.duration <= 12 + FRAME_S for s in segs)
    speech_samples = sum(int((s.audio > 0.05).sum()) for s in segs)
    assert speech_samples == pytest.approx(30 * SAMPLE_RATE, abs=2 * 512)


def test_chunk_size_does_not_change_result():
    audio = signal((1, False), (1.5, True), (1, False), (0.8, True), (1, False))
    a = run(audio, Segmenter("mic", fake_vad), block_s=0.01)
    b = run(audio, Segmenter("mic", fake_vad), block_s=0.37)
    assert [len(s.audio) for s in a] == [len(s.audio) for s in b]
