from hylive.output import clock, format_block
from hylive.textnorm import normalize_hy


def test_block_has_time_speaker_hy_en():
    block = format_block(72, "Speaker 1", "Բարև, ինչպե՞ս ես։", "Hi, how are you?")
    assert block.splitlines() == [
        "[00:01:12] Speaker 1",
        "  HY: Բարև, ինչպե՞ս ես։",
        "  EN: Hi, how are you?",
    ]


def test_block_with_timings():
    block = format_block(0, "Me", "x", "y", {"asr": 0.5, "mt": 0.25, "total": 1.4}, note="")
    assert "(latency 1.40s = asr 0.50 + mt 0.25)" in block


def test_clock():
    assert clock(3725.9) == "01:02:05"


def test_normalize_removes_punctuation_but_keeps_words_whole():
    assert normalize_hy("Բարև, ինչպե՞ս ես։") == "բարեվ ինչպես ես"


def test_normalize_treats_spellings_of_and_alike():
    assert normalize_hy("ԵՎ") == normalize_hy("և") == normalize_hy("եւ")
