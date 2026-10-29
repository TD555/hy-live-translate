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


def test_empty_transcript_prints_nothing():
    p, out = make(asr_text="")
    p.process(seg("system"), emitted_at=7.5)
    assert out.getvalue() == ""
