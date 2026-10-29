"""Audio sources. Each one yields AudioChunks (16 kHz mono float32).

- LiveSource: a WASAPI device opened with PyAudioWPatch. This is either a microphone or a *loopback*
  device, which records what the speakers play (the other side of the call).
- FileSource: plays an audio file in real time, so the whole pipeline can be tested without a call.

Both have the same interface: read(timeout) -> AudioChunk | None, .done, .name, close().
"""

import queue
import sys
import time

import numpy as np
import soxr

from hylive import SAMPLE_RATE
from hylive.types import AudioChunk


def _pyaudio():
    try:
        import pyaudiowpatch
    except ImportError as e:
        raise RuntimeError(
            "Live capture needs PyAudioWPatch, which is Windows-only: pip install PyAudioWPatch"
        ) from e
    return pyaudiowpatch


def _wasapi_devices(p, pyaudio):
    wasapi = p.get_host_api_info_by_type(pyaudio.paWASAPI)
    devices = [p.get_device_info_by_index(i) for i in range(p.get_device_count())]
    devices = [d for d in devices if d["hostApi"] == wasapi["index"] and d["maxInputChannels"] > 0]
    return wasapi, devices


def _default_loopback(p, wasapi, devices):
    """The loopback twin of the default output device (same name + ' [Loopback]')."""
    speakers = p.get_device_info_by_index(wasapi["defaultOutputDevice"])
    for d in devices:
        if d.get("isLoopbackDevice") and speakers["name"] in d["name"]:
            return d
    raise RuntimeError(
        f"No loopback device found for the default output '{speakers['name']}'. "
        "Run with --list-devices and pass --system <index>."
    )


def list_devices() -> None:
    pyaudio = _pyaudio()
    with pyaudio.PyAudio() as p:
        wasapi, devices = _wasapi_devices(p, pyaudio)
        default_loop = _default_loopback(p, wasapi, devices)["index"]
        print("WASAPI input devices (use the index with --mic / --system):\n")
        print(f"  {'idx':>4}  {'kind':<9} {'ch':>2} {'rate':>6}  name")
        for d in devices:
            loop = bool(d.get("isLoopbackDevice"))
            kind = "loopback" if loop else "mic"
            mark = ""
            if d["index"] == wasapi["defaultInputDevice"]:
                mark = "   <- default --mic"
            elif d["index"] == default_loop:
                mark = "   <- default --system"
            print(
                f"  {d['index']:>4}  {kind:<9} {d['maxInputChannels']:>2} "
                f"{int(d['defaultSampleRate']):>6}  {d['name']}{mark}"
            )


def resolve_device(kind: str, arg: str) -> int:
    """Turn the --mic/--system argument ('default' or an index) into a checked device index."""
    pyaudio = _pyaudio()
    with pyaudio.PyAudio() as p:
        wasapi, devices = _wasapi_devices(p, pyaudio)
        if arg == "default":
            if kind == "system":
                return _default_loopback(p, wasapi, devices)["index"]
            return wasapi["defaultInputDevice"]
        index = int(arg)
        match = [d for d in devices if d["index"] == index]
        if not match:
            raise SystemExit(f"--{kind} {index}: not a WASAPI input device. See --list-devices.")
        is_loop = bool(match[0].get("isLoopbackDevice"))
        if kind == "system" and not is_loop:
            raise SystemExit(f"--system {index} is a microphone, not a loopback device. See --list-devices.")
        if kind == "mic" and is_loop:
            raise SystemExit(f"--mic {index} is a loopback device, not a microphone. See --list-devices.")
        return index


class LiveSource:
    def __init__(self, device_index: int, block_s: float = 0.05):
        pyaudio = _pyaudio()
        self._pa_continue = pyaudio.paContinue
        self._p = pyaudio.PyAudio()
        info = self._p.get_device_info_by_index(device_index)
        self.name = info["name"]
        self.done = False  # a live device never runs out
        self._rate = int(info["defaultSampleRate"])
        self._channels = int(info["maxInputChannels"])
        self._resampler = soxr.ResampleStream(self._rate, SAMPLE_RATE, 1, dtype="float32")
        self._raw: queue.Queue = queue.Queue()
        self._warned = False
        # WASAPI shared mode: we must use the device's own rate and channel count, then convert.
        self._stream = self._p.open(
            format=pyaudio.paInt16,
            channels=self._channels,
            rate=self._rate,
            input=True,
            input_device_index=device_index,
            frames_per_buffer=int(self._rate * block_s),
            stream_callback=self._callback,
        )

    def _callback(self, in_data, frame_count, time_info, status):
        if status and not self._warned:
            print(f"[audio] warning: '{self.name}' reported status {status} (input overflow?)", file=sys.stderr)
            self._warned = True
        self._raw.put((in_data, time.monotonic()))
        return (None, self._pa_continue)

    def read(self, timeout: float) -> AudioChunk | None:
        """Next chunk, or None if the device sent nothing for `timeout` seconds."""
        try:
            data, t = self._raw.get(timeout=timeout)
        except queue.Empty:
            return None
        x = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
        x = x.reshape(-1, self._channels).mean(axis=1)
        return AudioChunk(self._resampler.resample_chunk(x), t)

    def close(self) -> None:
        self._stream.stop_stream()
        self._stream.close()
        self._p.terminate()
        # Free the native resampler now; if it is still alive at interpreter exit,
        # nanobind prints "leaked instances" warnings.
        self._resampler = None


class FileSource:
    """Plays an audio file at real-time speed, then a little silence so the last phrase gets closed."""

    def __init__(self, path: str, block_s: float = 0.05, tail_silence_s: float = 2.0):
        import soundfile as sf

        audio, sr = sf.read(path, dtype="float32", always_2d=True)
        audio = soxr.resample(audio.mean(axis=1), sr, SAMPLE_RATE).astype(np.float32)
        self._audio = np.concatenate([audio, np.zeros(int(tail_silence_s * SAMPLE_RATE), np.float32)])
        self._block = int(block_s * SAMPLE_RATE)
        self._pos = 0
        self._t0: float | None = None
        self.name = path
        self.done = False

    def read(self, timeout: float) -> AudioChunk | None:
        if self._t0 is None:
            self._t0 = time.monotonic()
        if self._pos >= len(self._audio):
            self.done = True
            return None
        end = min(self._pos + self._block, len(self._audio))
        due = self._t0 + end / SAMPLE_RATE  # when this block would have finished playing
        time.sleep(max(0.0, due - time.monotonic()))
        chunk = AudioChunk(self._audio[self._pos : end], time.monotonic())
        self._pos = end
        return chunk

    def close(self) -> None:
        pass
