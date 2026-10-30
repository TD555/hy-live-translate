"""SpeakerSplitter with synthetic voices: voice A = positive samples, voice B = negative samples.

The fake embedder maps the share of A vs B samples in a window to a direction between two unit vectors,
so a window that straddles a speaker change gives a mixed embedding, like a real one would.
"""

import numpy as np
import pytest

from hylive import SAMPLE_RATE
from hylive.speakers import SpeakerSplitter
from hylive.types import Segment

E_A, E_B = np.eye(192)[0], np.eye(192)[1]


class FakeVoiceEmbedder:
    def embed(self, audio):
        return self.embed_batch([audio])[0]

    def embed_batch(self, windows):
        out = []
        for w in windows:
            voiced = w[np.abs(w) > 0.01]
            p = float((voiced > 0).mean()) if len(voiced) else 0.5
            v = p * E_A + (1 - p) * E_B
            out.append(v / np.linalg.norm(v))
        return np.array(out)


def track(*parts):
    """parts: (seconds, 'A' | 'B' | '-') -> audio; '-' is silence."""
    level = {"A": 0.3, "B": -0.3, "-": 0.0}
    return np.concatenate([np.full(int(s * SAMPLE_RATE), level[v], np.float32) for s, v in parts])


def segment(audio, audio_start=100.0, pad=0.2):
    dur = len(audio) / SAMPLE_RATE
    return Segment("system", audio, start_time=audio_start + pad, end_time=audio_start + dur - pad,
                   audio_start=audio_start)


def voice_of(piece):
    voiced = piece.audio[np.abs(piece.audio) > 0.01]
    return "A" if (voiced > 0).mean() > 0.5 else "B"


def splitter():
    return SpeakerSplitter(FakeVoiceEmbedder(), threshold=0.5)


def test_two_speakers_are_split_at_the_pause_between_them():
    seg = segment(track((0.2, "-"), (4, "A"), (0.1, "-"), (4, "B"), (0.2, "-")))
    pieces = splitter().split(seg)
    assert [voice_of(p) for p in pieces] == ["A", "B"]
    cut_s = pieces[1].audio_start - seg.audio_start
    assert 4.2 <= cut_s <= 4.3  # inside the 0.1 s gap, not in the middle of a word
    assert sum(len(p.audio) for p in pieces) == len(seg.audio)  # no audio lost
    assert pieces[0].start_time == seg.start_time and pieces[1].end_time == seg.end_time
    assert pieces[0].end_time == pytest.approx(pieces[1].audio_start)


def test_one_speaker_is_not_split():
    seg = segment(track((0.2, "-"), (8, "A"), (0.2, "-")))
    assert splitter().split(seg) == [seg]


def test_three_turns_give_three_pieces():
    seg = segment(track((0.2, "-"), (3, "A"), (3, "B"), (3, "A"), (0.2, "-")))
    assert [voice_of(p) for p in splitter().split(seg)] == ["A", "B", "A"]


def test_short_interjection_is_not_split_off():
    seg = segment(track((0.2, "-"), (6, "A"), (0.8, "B"), (0.2, "-")))
    assert len(splitter().split(seg)) == 1


@pytest.mark.parametrize("b_seconds", [0.6, 0.8, 1.0, 1.2, 1.4, 1.6, 2.0])
def test_no_piece_is_shorter_than_min_piece(b_seconds):
    # Strict threshold, so only the length rule can stop a cut. Pieces < 1.5 s are too short to
    # transcribe and identify reliably. (The cut position itself is only accurate to about ±0.25 s.)
    seg = segment(track((0.2, "-"), (6, "A"), (b_seconds, "B"), (0.2, "-")))
    pieces = SpeakerSplitter(FakeVoiceEmbedder(), threshold=0.9).split(seg)
    assert all(p.duration >= 1.5 for p in pieces)


def test_second_voice_of_1_5_s_or_more_is_split_off():
    seg = segment(track((0.2, "-"), (6, "A"), (1.3, "B"), (0.2, "-")))
    assert [voice_of(p) for p in splitter().split(seg)] == ["A", "B"]


def test_short_phrase_is_left_alone():
    seg = segment(track((0.2, "-"), (2, "A"), (0.2, "-")))
    assert splitter().split(seg) == [seg]


class NoisyOneVoiceEmbedder:
    """One speaker whose window embeddings vary, like real ones (cosine to the voice ≈ 0.8)."""

    def __init__(self):
        self.rng = np.random.default_rng(1)

    def embed(self, audio):
        return self.embed_batch([audio])[0]

    def embed_batch(self, windows):
        v = E_A + 0.75 * self.rng.normal(size=(len(windows), 192)) / np.sqrt(192)
        return v / np.linalg.norm(v, axis=1, keepdims=True)


def test_one_speaker_with_noisy_embeddings_is_not_split():
    seg = segment(track((0.2, "-"), (8, "A"), (0.2, "-")))
    assert SpeakerSplitter(NoisyOneVoiceEmbedder(), threshold=0.5).split(seg) == [seg]


def test_missing_audio_start_fails_loudly():
    seg = Segment("system", np.zeros(SAMPLE_RATE * 4, np.float32), start_time=0.0, end_time=4.0)
    with pytest.raises(ValueError):
        splitter().split(seg)
