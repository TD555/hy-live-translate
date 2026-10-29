"""Armenian text normalisation for WER/CER, so that punctuation and spelling variants don't count as errors."""

import unicodedata

# Armenian marks written *inside* a word (stress ՛, exclamation ՜, question ՞, apostrophe ՚, abbreviation ՟):
# delete them, otherwise "ինչպե՞ս" would split into two words.
IN_WORD_MARKS = {"՛", "՜", "՞", "՚", "՟"}


def normalize_hy(text: str) -> str:
    text = unicodedata.normalize("NFC", text).lower()
    # "and": the ligature և, its uppercase spelling ԵՎ (→ եվ after lower()) and the classical եւ are the same word
    text = text.replace("և", "եվ").replace("եւ", "եվ")
    out = []
    for ch in text:
        if ch in IN_WORD_MARKS:
            continue
        cat = unicodedata.category(ch)
        out.append(" " if cat[0] in "PS" else ch)  # other punctuation and symbols separate words
    return " ".join("".join(out).split())
