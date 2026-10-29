"""Armenian → English translation with NLLB-200 (Hugging Face transformers)."""

import re

# Sentence end: Armenian full stop ։, ASCII colon (often typed instead of ։), . ! ? …, followed by a space.
_SENTENCE_END = re.compile(r"(?<=[։:.!?…])\s+")


def split_sentences(text: str) -> list[str]:
    """NLLB is trained on single sentences; given a paragraph it tends to drop parts of it."""
    parts = [p.strip(" -–—") for p in _SENTENCE_END.split(text)]
    return [p for p in parts if p]


class NllbTranslator:
    SRC, TGT = "hye_Armn", "eng_Latn"  # NLLB language codes

    def __init__(self, model_id: str, device: str, dtype, num_beams: int = 4):
        import torch
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

        self._torch = torch
        self.device = device
        self.num_beams = num_beams
        self.tokenizer = AutoTokenizer.from_pretrained(model_id, src_lang=self.SRC)
        self.model = AutoModelForSeq2SeqLM.from_pretrained(model_id, dtype=dtype).to(device).eval()
        self.tgt_id = self.tokenizer.convert_tokens_to_ids(self.TGT)

    def translate(self, text: str) -> str:
        sentences = split_sentences(text) or [text]
        inputs = self.tokenizer(sentences, return_tensors="pt", padding=True).to(self.device)
        n_in = inputs["input_ids"].shape[1]
        with self._torch.inference_mode():
            out = self.model.generate(
                **inputs,
                forced_bos_token_id=self.tgt_id,
                num_beams=self.num_beams,
                # Guards against the repetition loop seen live ("I'm in rap, I'm in rap, ..."):
                no_repeat_ngram_size=4,
                max_length=min(200, 2 * n_in + 10),  # English is rarely > 2x the Armenian token count
            )
        return " ".join(s.strip() for s in self.tokenizer.batch_decode(out, skip_special_tokens=True))
