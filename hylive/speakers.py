"""Telling call-side speakers apart.

EcapaEmbedder turns audio into a 192-dim voice embedding. SpeakerSplitter cuts a phrase where the voice
changes, so each piece holds one speaker. SpeakerTracker clusters the pieces online: each one goes to the
most similar known speaker, or becomes a new speaker if nobody is similar enough. Labels are numbered in
order of first appearance and never change during the session.
"""

import numpy as np

from hylive import SAMPLE_RATE
from hylive.types import Segment


def _cos(a: np.ndarray, b: np.ndarray) -> float:
    return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b)))


def two_voices(embs: np.ndarray, iters: int = 10) -> tuple[np.ndarray, float]:
    """Group unit window embeddings into 2 clusters (2-means on cosine).

    Returns (label 0/1 per window, cosine similarity of the two centroids). Starts from the two least
    similar windows. If everything ends up in one cluster, the similarity is 1.0.
    """
    sims = embs @ embs.T
    i, j = np.unravel_index(np.argmin(sims), sims.shape)
    centroids = np.stack([embs[i], embs[j]])
    labels = np.zeros(len(embs), dtype=int)
    for _ in range(iters):
        labels = np.argmax(embs @ centroids.T, axis=1)
        if labels.min() == labels.max():
            return labels, 1.0
        new = np.stack([embs[labels == k].mean(axis=0) for k in (0, 1)])
        new /= np.linalg.norm(new, axis=1, keepdims=True)
        if np.allclose(new, centroids):
            break
        centroids = new
    return labels, _cos(centroids[0], centroids[1])


def quiet_point(audio: np.ndarray, center: int, radius: int, frame: int = 320) -> int:
    """Sample index of the quietest 20 ms within ±radius of center, so a cut doesn't land mid-word."""
    lo, hi = max(0, center - radius), min(len(audio) - frame, center + radius)
    if hi <= lo:
        return center
    start = min(range(lo, hi, frame // 2), key=lambda s: float(np.mean(audio[s : s + frame] ** 2)))
    return start + frame // 2


class SpeakerSplitter:
    """Splits a call-side phrase where the voice changes, so each piece holds one speaker.

    1. Embed windows of `win_s` every `hop_s` (one GPU batch).
    2. Group the windows into two voices; if the two groups sound alike (centroid cosine >= `threshold`),
       it's one speaker: no split.
    3. Cut where the window label changes, and move each cut to the quietest 20 ms nearby.
    4. Drop cuts that leave a piece shorter than `min_piece_s`, and merge neighbouring pieces whose
       whole-piece embeddings are still similar (>= `threshold`).
    Handles any number of turns between *two* voices inside one phrase. Speech where both people talk at
    the same time can't be separated this way.
    """

    def __init__(self, embedder, threshold: float = 0.5, win_s: float = 1.5, hop_s: float = 0.5,
                 min_piece_s: float = 1.5):
        self.embedder = embedder
        self.threshold = threshold
        self.win, self.hop = int(win_s * SAMPLE_RATE), int(hop_s * SAMPLE_RATE)
        self.min_piece = int(min_piece_s * SAMPLE_RATE)
        self.min_windows = 4  # below this (≈ 3 s of audio) a phrase is too short to hold two pieces

    def split(self, seg: Segment) -> list[Segment]:
        if seg.audio_start is None:
            raise ValueError("Segment.audio_start is required to split a phrase")
        cuts = self._cuts(seg.audio)
        if not cuts:
            return [seg]
        edges = [0] + cuts + [len(seg.audio)]
        return [self._piece(seg, edges[i], edges[i + 1]) for i in range(len(edges) - 1)]

    def _cuts(self, audio: np.ndarray) -> list[int]:
        n = len(audio)
        if n < 2 * self.min_piece:
            return []
        starts = list(range(0, n - self.win + 1, self.hop))
        if starts[-1] != n - self.win:
            starts.append(n - self.win)  # last window ends exactly at the end
        if len(starts) < self.min_windows:
            return []
        embs = self.embedder.embed_batch([audio[s : s + self.win] for s in starts])
        labels, centroid_sim = two_voices(embs)
        if centroid_sim >= self.threshold:
            return []  # shortcut for the common case (one voice); step 4 would also merge these pieces
        changes = [k for k in range(1, len(labels)) if labels[k] != labels[k - 1]]
        cuts = [quiet_point(audio, (starts[k - 1] + starts[k] + self.win) // 2, self.hop // 2) for k in changes]

        # pieces must be long enough to transcribe and to identify the speaker
        cuts = [c for c in cuts if self.min_piece <= c <= n - self.min_piece]
        kept: list[int] = []
        for c in cuts:
            if not kept or c - kept[-1] >= self.min_piece:
                kept.append(c)

        # final check on whole pieces: merge neighbours that still sound like the same person
        edges = [0] + kept + [n]
        pieces = [audio[edges[i] : edges[i + 1]] for i in range(len(edges) - 1)]
        embs = [self.embedder.embed(p) for p in pieces]
        return [kept[i] for i in range(len(kept)) if _cos(embs[i], embs[i + 1]) < self.threshold]

    @staticmethod
    def _piece(seg: Segment, a: int, b: int) -> Segment:
        t0 = seg.audio_start + a / SAMPLE_RATE
        t1 = seg.audio_start + b / SAMPLE_RATE
        start = max(seg.start_time, t0)
        end = max(start, min(seg.end_time, t1))
        return Segment(seg.source, seg.audio[a:b], start_time=start, end_time=end, audio_start=t0)


class EcapaEmbedder:
    SOURCE = "speechbrain/spkrec-ecapa-voxceleb"

    def __init__(self, device: str, savedir: str):
        import torch
        from speechbrain.inference.classifiers import EncoderClassifier
        from speechbrain.utils.fetching import LocalStrategy

        self._torch = torch
        self.device = device
        # SpeechBrain wants an explicit index ("cuda:0"); plain "cuda" logs a parse warning.
        sb_device = "cuda:0" if device == "cuda" else device
        # COPY instead of the default SYMLINK: symlinks need admin rights / developer mode on Windows.
        self.model = EncoderClassifier.from_hparams(
            source=self.SOURCE, savedir=savedir, run_opts={"device": sb_device}, local_strategy=LocalStrategy.COPY
        )
        self.model.eval()

    def embed(self, audio: np.ndarray) -> np.ndarray:
        return self.embed_batch([audio])[0]

    def embed_batch(self, windows: list[np.ndarray]) -> np.ndarray:
        """Equal-length audio windows -> (n, 192) array of unit vectors, in one GPU call."""
        wav = self._torch.from_numpy(np.stack(windows)).to(self.device)
        with self._torch.inference_mode():
            emb = self.model.encode_batch(wav)  # (n, 1, 192)
        v = emb.reshape(len(windows), -1).float().cpu().numpy()
        return v / np.linalg.norm(v, axis=1, keepdims=True)


class SpeakerTracker:
    """Online clustering of phrase embeddings.

    threshold:  minimum cosine similarity to a speaker's centroid to count as that speaker.
                0.5 from the 2026-10-30 interview replay: same-speaker phrases scored 0.56–0.85.
    min_new_s:  phrases with less speech than this give unreliable embeddings. They are matched to the
                closest existing speaker but never create a new one or change a centroid.
    """

    def __init__(self, threshold: float = 0.5, min_new_s: float = 1.0):
        self.threshold = threshold
        self.min_new_s = min_new_s
        self._sums: list[np.ndarray] = []  # running sum of unit embeddings per speaker

    @property
    def n_speakers(self) -> int:
        return len(self._sums)

    def assign(self, embedding: np.ndarray, duration_s: float) -> tuple[int, float]:
        """Return (speaker number starting at 1, similarity to that speaker's centroid)."""
        e = embedding / np.linalg.norm(embedding)
        if not self._sums:
            self._sums.append(e.copy())
            return 1, 1.0

        sims = [float(e @ (s / np.linalg.norm(s))) for s in self._sums]
        best = int(np.argmax(sims))
        reliable = duration_s >= self.min_new_s

        if sims[best] >= self.threshold:
            if reliable:
                self._sums[best] += e
            return best + 1, sims[best]
        if not reliable:
            return best + 1, sims[best]
        self._sums.append(e.copy())
        return len(self._sums), sims[best]
