"""PhraseProcessor with fake models: checks labels and output, not model quality."""

import io

import numpy as np

from hylive.output import Printer
from hylive.pipeline import PhraseProcessor
from hylive.speakers import SpeakerTracker
from hylive.types import Segment


class FakeAsr:
    def __init__(self, text="Բարև"):
        self.text = text

    def transcribe(self, audio):
        return self.text


class FakeMt:
    def translate(self, text):
        return "Hello"


class FakeEmbedder:
    def embed(self, audio):
        return np.ones(192)


def make(asr_text="Բարև"):
    out = io.StringIO()
    p = PhraseProcessor(FakeAsr(asr_text), FakeMt(), FakeEmbedder(), SpeakerTracker(), Printer(stream=out), 0.0)
    return p, out


def seg(source, start=5.0):
    return Segment(source, np.zeros(16000 * 2, np.float32), start_time=start, end_time=start + 2)


def test_mic_is_always_me_and_system_gets_speaker_number():
    p, out = make()
    p.process(seg("mic"), emitted_at=7.5)
    p.process(seg("system", 10.0), emitted_at=12.5)
    text = out.getvalue()
    assert "[00:00:05] Me\n  HY: Բարև\n  EN: Hello" in text
    assert "[00:00:10] Speaker 1" in text


class TwoVoiceEmbedder:
    """First call returns voice A, later calls an unrelated voice B."""

    def __init__(self):
        self.calls = 0

    def embed(self, audio):
        self.calls += 1
        v = np.zeros(192)
        v[0 if self.calls == 1 else 1] = 1.0
        return v


def test_one_word_phrase_with_padding_does_not_create_a_speaker():
    # Bug seen live: 0.6 s of speech + 0.4 s padding = 1.0 s of audio passed the "long enough" check.
    out = io.StringIO()
    p = PhraseProcessor(FakeAsr(), FakeMt(), TwoVoiceEmbedder(), SpeakerTracker(min_new_s=1.0),
                        Printer(stream=out), 0.0)
    p.process(seg("system", 5.0), emitted_at=7.5)  # 2 s of speech: Speaker 1
    word = Segment("system", np.zeros(16000, np.float32), start_time=10.0, end_time=10.6)
    p.process(word, emitted_at=11.0)
    assert "Speaker 2" not in out.getvalue()


def test_empty_transcript_prints_nothing():
    p, out = make(asr_text="")
    p.process(seg("system"), emitted_at=7.5)
    assert out.getvalue() == ""
