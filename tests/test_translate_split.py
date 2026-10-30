from hylive.translate import split_sentences


def test_splits_on_armenian_and_ascii_sentence_ends():
    text = "Ես էլ եմ ուզում գալ։ Դու գալի՞ս ես: Լավ"
    assert split_sentences(text) == ["Ես էլ եմ ուզում գալ։", "Դու գալի՞ս ես:", "Լավ"]


def test_strips_dialogue_dashes_seen_in_live_asr_output():
    text = "- Ես գնում եմ: - Շատ լավ ա:"
    assert split_sentences(text) == ["Ես գնում եմ:", "Շատ լավ ա:"]


def test_in_word_question_mark_does_not_split():
    assert split_sentences("ինչպե՞ս ես") == ["ինչպե՞ս ես"]


def test_text_without_punctuation_stays_whole():
    assert split_sentences("ուղղակի պապան չի ուզում շատ աշխատի") == ["ուղղակի պապան չի ուզում շատ աշխատի"]
