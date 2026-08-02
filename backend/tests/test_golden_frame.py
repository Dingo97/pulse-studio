import json

import numpy as np
import pytest

pytest.importorskip("cv2")
from app.renderer import lyric_card
from app.schemas import EditorSettings


EXPECTED = {
    "landscape": {"shape": [1080, 1920, 4], "bbox": [1005, 523, 1740, 733], "alpha_pixels": 135376, "accent_pixels": 6639},
    "vertical": {"shape": [1920, 1080, 4], "bbox": [46, 1272, 998, 1482], "alpha_pixels": 149738, "accent_pixels": 6639},
}


def _signature(frame: np.ndarray, accent: tuple[int, int, int]) -> dict:
    alpha = frame[:, :, 3] > 0
    ys, xs = np.where(alpha)
    return {
        "shape": list(frame.shape),
        "bbox": [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())],
        "alpha_pixels": int(alpha.sum()),
        "accent_pixels": int(np.all(frame[:, :, :3] == accent, axis=2).sum()),
    }


def test_classic_pulse_golden_frames() -> None:
    settings = EditorSettings()
    payload = settings.model_dump_json()
    text = "THIS IS A GOLDEN LYRIC FRAME"
    landscape = lyric_card(text, 3, 1920, 1080, True, "youtube", payload)
    vertical = lyric_card(text, 3, 1080, 1920, False, "tiktok", payload)
    actual = {
        "landscape": _signature(landscape, (255, 138, 76)),
        "vertical": _signature(vertical, (255, 138, 76)),
    }
    assert actual == EXPECTED, json.dumps(actual, indent=2)


def test_drag_coordinates_move_lyrics_in_both_axes() -> None:
    base = EditorSettings(lyrics_x_landscape=.35, lyrics_y_landscape=.35)
    moved = EditorSettings(lyrics_x_landscape=.65, lyrics_y_landscape=.65)
    first = _signature(lyric_card("DRAGGABLE LYRICS", 0, 1280, 720, True, "youtube", base.model_dump_json()), (255, 138, 76))["bbox"]
    second = _signature(lyric_card("DRAGGABLE LYRICS", 0, 1280, 720, True, "youtube", moved.model_dump_json()), (255, 138, 76))["bbox"]
    assert second[0] > first[0]
    assert second[1] > first[1]


def test_reference_word_styles_have_distinct_rendered_layouts() -> None:
    text = "Every word should move with a different visual rhythm"
    frames = {
        style: lyric_card(text, 3, 1280, 720, True, "youtube", EditorSettings(word_animation=style).model_dump_json())
        for style in ("constellation", "impact", "ink")
    }
    assert all(np.count_nonzero(frame[:, :, 3]) > 1000 for frame in frames.values())
    assert not np.array_equal(frames["constellation"], frames["impact"])
    assert not np.array_equal(frames["impact"], frames["ink"])


def test_ink_reveal_adds_words_as_timing_advances() -> None:
    settings = EditorSettings(word_animation="ink")
    first = lyric_card("One word at a time", 0, 1280, 720, True, "youtube", settings.model_dump_json())
    later = lyric_card("One word at a time", 3, 1280, 720, True, "youtube", settings.model_dump_json())
    assert np.count_nonzero(later[:, :, 3]) > np.count_nonzero(first[:, :, 3])
