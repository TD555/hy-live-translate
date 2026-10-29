"""Armenian → English translation with NLLB-200 (Hugging Face transformers)."""


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
        inputs = self.tokenizer(text, return_tensors="pt").to(self.device)
        with self._torch.inference_mode():
            # length limit comes from the model's generation config (max_length=200 tokens)
            out = self.model.generate(**inputs, forced_bos_token_id=self.tgt_id, num_beams=self.num_beams)
        return self.tokenizer.batch_decode(out, skip_special_tokens=True)[0].strip()
