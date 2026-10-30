"""Cut a stream of audio into phrases using a voice-activity detector.

The segmenter itself is pure logic. It takes a `speech_prob(frame) -> float` function, so it can be
tested with a fake VAD. `SileroVad` provides the real one.
"""

from collections import deque
from typing import Callable

import numpy as np

from hylive import SAMPLE_RATE
from hylive.types import AudioChunk, Segment

FRAME = 512  # samples per VAD frame; Silero requires exactly 512 at 16 kHz (32 ms)
FRAME_S = FRAME / SAMPLE_RATE


class SileroVad:
    """Speech probability for one 512-sample frame. Stateful: use one instance per audio source."""

    def __init__(self):
        import torch
        from silero_vad import load_silero_vad

        self._torch = torch
        self._model = load_silero_vad()

    def __call__(self, frame: np.ndarray) -> float:
        with self._torch.inference_mode():
            return self._model(self._torch.from_numpy(frame), SAMPLE_RATE).item()


class Segmenter:
    """Turns AudioChunks into Segments (one per phrase).

    A phrase starts at the first frame with speech probability >= threshold, and ends after
    `min_silence_s` of frames below the threshold. Phrases shorter than `min_speech_s` are dropped.
    Phrases longer than `max_segment_s` are cut, and the next segment continues straight on.
    `pad_s` of audio before and after the speech is kept, because ASR does better with a little context.
    """

    def __init__(
        self,
        source: str,
        speech_prob: Callable[[np.ndarray], float],
        threshold: float = 0.5,
        min_silence_s: float = 0.5,
        min_speech_s: float = 0.3,
        max_segment_s: float = 12.0,
        pad_s: float = 0.2,
    ):
        self.source = source
        self.speech_prob = speech_prob
        self.threshold = threshold
        self.min_silence_frames = round(min_silence_s / FRAME_S)
        self.min_speech_frames = round(min_speech_s / FRAME_S)
        self.max_frames = round(max_segment_s / FRAME_S)
        self.pad_frames = round(pad_s / FRAME_S)

        self._pending = np.zeros(0, dtype=np.float32)  # samples not yet forming a full frame
        self._preroll: deque[np.ndarray] = deque(maxlen=self.pad_frames)
        self._frames: list[np.ndarray] = []  # frames of the current phrase
        self._last_speech_idx = -1  # index in _frames of the last speech frame
        self._speech_count = 0
        self._start_time = 0.0
        self._last_speech_time = 0.0
        self._last_frame_time = 0.0
        self._audio_start = 0.0
        self._in_phrase = False

    def push(self, chunk: AudioChunk) -> list[Segment]:
        audio = np.concatenate([self._pending, chunk.samples.astype(np.float32, copy=False)])
        n_frames = len(audio) // FRAME
        self._pending = audio[n_frames * FRAME :]
        out = []
        for i in range(n_frames):
            frame = audio[i * FRAME : (i + 1) * FRAME]
            # wall-clock time at the end of this frame
            samples_after = len(audio) - (i + 1) * FRAME
            t_end = chunk.end_time - samples_after / SAMPLE_RATE
            seg = self._step(frame, t_end)
            if seg is not None:
                out.append(seg)
        return out

    def _step(self, frame: np.ndarray, t_end: float) -> Segment | None:
        is_speech = self.speech_prob(frame) >= self.threshold

        if not self._in_phrase:
            if is_speech:
                self._in_phrase = True
                self._frames = list(self._preroll)
                self._preroll.clear()
                self._start_time = t_end - FRAME_S
                self._audio_start = self._start_time - len(self._frames) * FRAME_S  # pre-roll comes first
                self._speech_count = 0
                self._add(frame, t_end, is_speech)
            else:
                self._preroll.append(frame)
            return None

        self._add(frame, t_end, is_speech)
        silence_frames = len(self._frames) - 1 - self._last_speech_idx
        if silence_frames >= self.min_silence_frames:
            return self._finish(continue_phrase=False)
        if len(self._frames) >= self.max_frames:
            return self._finish(continue_phrase=True)
        return None

    def _add(self, frame: np.ndarray, t_end: float, is_speech: bool) -> None:
        self._frames.append(frame)
        self._last_frame_time = t_end
        if is_speech:
            self._last_speech_idx = len(self._frames) - 1
            self._last_speech_time = t_end
            self._speech_count += 1

    def _finish(self, continue_phrase: bool) -> Segment | None:
        if continue_phrase:
            # Forced cut of a long phrase: emit everything so far; the next segment starts at the cut.
            frames = self._frames
        else:
            # Phrase ended in silence: keep `pad_frames` of the trailing silence.
            frames = self._frames[: self._last_speech_idx + 1 + self.pad_frames]

        seg = None
        if self._speech_count >= self.min_speech_frames:
            seg = Segment(
                source=self.source,
                audio=np.concatenate(frames),
                start_time=self._start_time,
                end_time=self._last_speech_time,
                audio_start=self._audio_start,
            )

        if continue_phrase:
            self._start_time = self._last_frame_time
            self._audio_start = self._last_frame_time
        else:
            self._in_phrase = False
            self._preroll.clear()  # refills with the silence that follows
        self._frames = []
        self._last_speech_idx = -1
        self._speech_count = 0
        return seg
