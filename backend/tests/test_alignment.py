from app.alignment import TimedWord, _is_section_label, _map_lines, _map_words, _mapped_token_times, _merge_elisions


def _heard(words: list[str]) -> list[TimedWord]:
    return [TimedWord(word, index * .4, index * .4 + .25) for index, word in enumerate(words)]


def test_repeated_chorus_occurrences_remain_monotonic() -> None:
    target = "prima strofa canta forte stesso ritornello seconda strofa cambia tutto stesso ritornello".split()
    heard = _heard("prima strofa canta forte stesso ritornello seconda strofa cambia tutto stesso ritornello".split())
    mapping, matched = _map_words(target, heard)
    assert mapping == sorted(mapping)
    assert all(matched)
    assert mapping[4] < mapping[-2]


def test_missing_words_are_interpolated_between_real_anchors() -> None:
    mapping, matched = _map_words("questa parola non viene sentita ora".split(), _heard("questa parola sentita ora".split()))
    assert mapping == sorted(mapping)
    assert matched[0] and matched[-1]
    assert not all(matched)


def test_section_headers_are_not_treated_as_lyrics() -> None:
    assert _is_section_label("[Chorus]")
    assert _is_section_label("Strofa 2:")
    assert not _is_section_label("Questo è il mio ritornello")


def test_italian_elisions_are_rejoined_before_mapping() -> None:
    words = [TimedWord("l", 12.06, 12.9), TimedWord("ombra", 12.9, 13.74), TimedWord("dell", 15.1, 15.3), TimedWord("alba", 15.3, 15.72)]
    merged = _merge_elisions(words, "it")
    assert [word.text for word in merged] == ["lombra", "dellalba"]
    assert merged[0].start == 12.06 and merged[-1].end == 15.72


def test_line_cursor_keeps_repeated_choruses_separate() -> None:
    lines = ["fantasma dove sei".split(), "in mezzo a questa gente".split(), "cuore scappato via".split(), "fantasma dove sei".split(), "in mezzo a questa gente".split()]
    target = [word for line in lines for word in line]
    ranges = []
    cursor = 0
    for line in lines:
        ranges.append((cursor, cursor + len(line)))
        cursor += len(line)
    heard = _heard(target)
    mapping, matched = _map_lines(target, ranges, heard)
    assert all(matched)
    assert mapping == list(range(len(target)))
    assert mapping[ranges[1][0]] < mapping[ranges[4][0]]


def test_merged_whisper_word_is_split_across_lyric_words() -> None:
    target = ["un", "solo", "livido"]
    heard = [TimedWord("unsolo", 3.32, 3.70), TimedWord("livido", 3.70, 4.16)]
    timings = _mapped_token_times(target, 0, 3, [0, 0, 1], heard, 3.30, 4.18)
    assert timings[0][1] <= timings[1][0]
    assert timings[1][1] == 3.70
    assert timings[2] == (3.70, 4.16)
