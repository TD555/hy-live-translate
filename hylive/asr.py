"""Armenian speech recognition with a Whisper-architecture model (Hugging Face transformers)."""

import numpy as np

from hylive import SAMPLE_RATE


class WhisperAsr:
    """Transcribes one phrase (16 kHz float32) to Armenian text.

    language: None for models whose generation config already forces Armenian (BuzzASR/armenian
              says so on its model card). Use "hy" for multilingual checkpoints such as
              openai/whisper-large-v3 or Chillarmo/whisper-large-v3-turbo-armenian.
    """

    def __init__(self, model_id: str, device: str, dtype, language: str | None = None, num_beams: int = 1):
        import torch
        from transformers import WhisperForConditionalGeneration, WhisperProcessor

        self._torch = torch
        self.device, self.dtype = device, dtype
        self.processor = WhisperProcessor.from_pretrained(model_id)
        self.model = WhisperForConditionalGeneration.from_pretrained(model_id, dtype=dtype).to(device).eval()
        # Settings from the BuzzASR model card; the repetition guards also help against
        # Whisper's habit of looping on noise.
        self.gen_kwargs = dict(num_beams=num_beams, no_repeat_ngram_size=3, repetition_penalty=1.2)
        if language:
            self.gen_kwargs.update(language=language, task="transcribe")

    def transcribe(self, audio: np.ndarray) -> str:
        feats = self.processor(audio, sampling_rate=SAMPLE_RATE, return_tensors="pt").input_features
        feats = feats.to(self.device, self.dtype)
        with self._torch.inference_mode():
            ids = self.model.generate(feats, **self.gen_kwargs)
        return self.processor.batch_decode(ids, skip_special_tokens=True)[0].strip()
