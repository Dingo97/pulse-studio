import numpy as np
import pytest

pytest.importorskip("cv2")
from app.renderer import PulseRenderer, _safe_rect
from app.media import AudioProfile
from app.schemas import EditorSettings


def test_tiktok_safe_area_is_more_conservative_than_shorts() -> None:
    tiktok = _safe_rect(1080, 1920, "tiktok")
    shorts = _safe_rect(1080, 1920, "shorts")
    assert tiktok[2] <= shorts[2]
    assert tiktok[3] <= shorts[3]


def test_smart_crop_returns_exact_target_size() -> None:
    source = np.zeros((720, 1280, 3), dtype=np.uint8)
    source[:, 900:1100] = 255
    cropped = PulseRenderer._crop_fill(source, 360, 640, True)
    assert cropped.shape == (640, 360, 3)


def test_continuous_smart_crop_keeps_one_window_across_video_frames() -> None:
    first = np.zeros((360, 640, 3), dtype=np.uint8)
    second = np.zeros_like(first)
    checker = (np.indices((360, 160)).sum(axis=0) % 2 * 255).astype(np.uint8)
    first[:, :160] = checker[:, :, None]
    second[:, -160:] = checker[:, :, None]
    _, first_x, _, _, _ = PulseRenderer._crop_geometry(first, 180, 320, True)
    _, second_x, _, _, _ = PulseRenderer._crop_geometry(second, 180, 320, True)
    assert first_x != second_x
    renderer = PulseRenderer.__new__(PulseRenderer)
    renderer._stable_crop_positions = {}
    renderer._stable_crop_fill(first, 180, 320)
    original_window = dict(renderer._stable_crop_positions)
    renderer._stable_crop_fill(second, 180, 320)
    assert renderer._stable_crop_positions == original_window


@pytest.mark.parametrize("overlay", ["scratches", "light_leaks", "film_burn", "rain", "scanlines", "vhs", "bokeh", "prism"])
def test_dynamic_overlays_modify_frame_without_changing_shape(overlay: str) -> None:
    renderer = PulseRenderer.__new__(PulseRenderer)
    renderer.settings = EditorSettings(overlay=overlay, overlay_intensity=70)
    renderer.profile = AudioProfile(10, 120, np.array([1.0, 1.5], dtype=np.float32))
    frame = np.full((180, 320, 3), 96, dtype=np.uint8)
    rendered = renderer._finish(frame, 1.02)
    assert rendered.shape == frame.shape
    assert not np.array_equal(rendered, frame)
