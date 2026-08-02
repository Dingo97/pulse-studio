from pathlib import Path

from app.media import load_lyrics


def test_srt_parser(tmp_path: Path) -> None:
    subtitle = tmp_path / "lyrics.srt"
    subtitle.write_text(
        "1\n00:00:01,000 --> 00:00:03,500\nFirst line\n\n"
        "2\n00:00:04,000 --> 00:00:06,000\nSecond line\n",
        encoding="utf-8",
    )
    cues = load_lyrics(subtitle, 10)
    assert [(cue.start, cue.end, cue.text) for cue in cues] == [
        (1.0, 3.5, "First line"),
        (4.0, 6.0, "Second line"),
    ]


def test_plain_text_is_distributed(tmp_path: Path) -> None:
    lyrics = tmp_path / "lyrics.txt"
    lyrics.write_text("One\nTwo\n", encoding="utf-8")
    cues = load_lyrics(lyrics, 20)
    assert cues[0].start == 0
    assert cues[1].start == 10
