"""Telling call-side speakers apart.

EcapaEmbedder turns a phrase into a 192-dim voice embedding. SpeakerTracker clusters these online:
each phrase goes to the most similar known speaker, or becomes a new speaker if nobody is similar enough.
Labels are numbered in order of first appearance and never change during the session.
"""

import numpy as np


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
        wav = self._torch.from_numpy(audio).unsqueeze(0).to(self.device)
        with self._torch.inference_mode():
            emb = self.model.encode_batch(wav)
        v = emb.squeeze().float().cpu().numpy()
        return v / np.linalg.norm(v)


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
