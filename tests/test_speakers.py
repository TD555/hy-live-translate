"""SpeakerTracker with synthetic embeddings: each 'voice' is a random direction plus noise."""

import numpy as np

from hylive.speakers import SpeakerTracker

rng = np.random.default_rng(0)
VOICES = {name: rng.normal(size=192) for name in "ABC"}


def utterance(voice, noise=0.6):
    v = VOICES[voice] / np.linalg.norm(VOICES[voice])
    return v + noise * rng.normal(size=192) / np.sqrt(192)


def test_voices_get_stable_distinct_labels():
    t = SpeakerTracker(threshold=0.35)
    order = "ABACBBAC"
    labels = [t.assign(utterance(v), duration_s=2.0)[0] for v in order]
    assert labels == [1, 2, 1, 3, 2, 2, 1, 3]
    assert t.n_speakers == 3


def test_first_phrase_is_speaker_1_even_if_short():
    t = SpeakerTracker(min_new_s=1.0)
    assert t.assign(utterance("A"), duration_s=0.4)[0] == 1


def test_short_phrase_never_creates_a_speaker():
    t = SpeakerTracker(threshold=0.35, min_new_s=1.0)
    t.assign(utterance("A"), duration_s=2.0)
    label, _ = t.assign(utterance("B"), duration_s=0.5)  # a new voice, but too short to trust
    assert label == 1
    assert t.n_speakers == 1
    assert t.assign(utterance("B"), duration_s=2.0)[0] == 2  # long enough: now it becomes speaker 2
