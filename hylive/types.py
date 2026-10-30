"""Data passed between modules."""

from dataclasses import dataclass

import numpy as np

from hylive import SAMPLE_RATE


@dataclass
class AudioChunk:
    """A block of audio from one source.

    samples:  float32 mono, 16 kHz, range [-1, 1]
    end_time: time.monotonic() when the last sample was captured
    """

    samples: np.ndarray
    end_time: float


@dataclass
class Segment:
    """One phrase of speech from one source, as cut by the VAD."""

    source: str  # "mic" or "system"
    audio: np.ndarray  # float32 mono 16 kHz, including a little padding around the speech
    start_time: float  # time.monotonic() at the first speech frame
    end_time: float  # time.monotonic() at the end of the last speech frame (latency is measured from here)
    audio_start: float | None = None  # time.monotonic() at audio[0] (before the padding); needed to split a phrase

    @property
    def duration(self) -> float:
        """Length of the audio, including the padding around the speech."""
        return len(self.audio) / SAMPLE_RATE

    @property
    def speech_duration(self) -> float:
        """First speech frame to last speech frame, without padding."""
        return self.end_time - self.start_time
