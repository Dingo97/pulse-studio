from pathlib import Path

import cv2
import numpy as np

import app.main as main


def test_video_proxy_is_small_seekable_h264(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    target = tmp_path / "proxy.mp4"
    writer = cv2.VideoWriter(str(source), cv2.VideoWriter_fourcc(*"mp4v"), 30, (1280, 720))
    assert writer.isOpened()
    for index in range(12):
        frame = np.full((720, 1280, 3), index * 15, dtype=np.uint8)
        writer.write(frame)
    writer.release()

    assert main._create_video_proxy(source, target)

    capture = cv2.VideoCapture(str(target))
    assert capture.isOpened()
    assert int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)) <= 960
    assert int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)) <= 960
    assert round(capture.get(cv2.CAP_PROP_FPS)) == 24
    capture.release()
