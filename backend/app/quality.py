from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import cv2

from .media import LyricCue
from .renderer import _safe_rect, lyric_card
from .schemas import EditorSettings


def run_quality_control(video_paths: list[Path], audio_path: Path, lyrics: list[LyricCue], settings: EditorSettings) -> dict:
    checks: list[dict] = []
    warnings: list[str] = []
    for path in video_paths:
        result = _inspect_video(path)
        checks.append(result)
        warnings.extend(f"{path.name}: {message}" for message in result["warnings"])
    lyric_warnings = _inspect_lyrics(lyrics)
    lyric_warnings.extend(_inspect_text_layout(lyrics, settings))
    warnings.extend(lyric_warnings)
    peak = _audio_peak(audio_path)
    if peak is not None and peak > -.1:
        warnings.append(f"Source audio peak is {peak:.2f} dBFS; possible clipping")
    return {
        "version": 1,
        "passed": not warnings,
        "warnings": warnings,
        "audio_peak_dbfs": peak,
        "lyrics": {"cues": len(lyrics), "warnings": lyric_warnings},
        "videos": checks,
    }


def _inspect_video(path: Path) -> dict:
    warnings: list[str] = []
    probe = _probe(path)
    video_stream = next((stream for stream in probe.get("streams", []) if stream.get("codec_type") == "video"), {})
    audio_stream = next((stream for stream in probe.get("streams", []) if stream.get("codec_type") == "audio"), {})
    width, height = int(video_stream.get("width", 0)), int(video_stream.get("height", 0))
    codec = str(video_stream.get("codec_name", "unknown"))
    duration = float(probe.get("format", {}).get("duration", 0) or 0)
    if (width, height) not in {(1080, 1920), (1920, 1080)}:
        warnings.append(f"unexpected resolution {width}x{height}")
    if codec != "h264":
        warnings.append(f"unexpected video codec {codec}")
    if not audio_stream:
        warnings.append("missing audio stream")
    if duration <= .4:
        warnings.append("invalid duration")
    black_ratio = _black_frame_ratio(path, duration)
    if black_ratio > .25:
        warnings.append(f"{black_ratio * 100:.0f}% sampled frames are nearly black")
    return {"file": path.name, "width": width, "height": height, "duration": round(duration, 3), "video_codec": codec, "audio_codec": audio_stream.get("codec_name"), "black_frame_ratio": round(black_ratio, 3), "warnings": warnings}


def _probe(path: Path) -> dict:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return {}
    result = subprocess.run([ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)], capture_output=True, text=True, timeout=30, check=False)
    try:
        return json.loads(result.stdout)
    except ValueError:
        return {}


def _black_frame_ratio(path: Path, duration: float) -> float:
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        return 1.0
    black = 0
    samples = 10
    try:
        for index in range(samples):
            capture.set(cv2.CAP_PROP_POS_MSEC, max(0, duration * index / samples) * 1000)
            ok, frame = capture.read()
            if not ok or float(frame.mean()) < 6.0:
                black += 1
    finally:
        capture.release()
    return black / samples


def _inspect_lyrics(cues: list[LyricCue]) -> list[str]:
    warnings: list[str] = []
    for index, cue in enumerate(cues):
        if cue.end - cue.start < .22:
            warnings.append(f"Lyric cue {index + 1} is shorter than 220 ms")
        if len(cue.text) > 180:
            warnings.append(f"Lyric cue {index + 1} is unusually long")
        if index and cue.start < cues[index - 1].end - .02:
            warnings.append(f"Lyric cues {index} and {index + 1} overlap")
    return warnings


def _inspect_text_layout(cues: list[LyricCue], settings: EditorSettings) -> list[str]:
    warnings: list[str] = []
    payload = settings.model_dump_json()
    samples = sorted(cues, key=lambda cue: len(cue.text), reverse=True)[:20]
    for platform, width, height in (("youtube", 1920, 1080), ("tiktok", 1080, 1920)):
        safe = _safe_rect(width, height, platform if settings.safe_area == "auto" else settings.safe_area)
        for cue in samples:
            frame = lyric_card(cue.text, 0, width, height, width > height, platform, payload)
            mask = frame[:, :, 3] > 0
            if not mask.any():
                warnings.append(f"Empty lyric render for: {cue.text[:40]}")
                continue
            ys, xs = mask.nonzero()
            if xs.min() < safe[0] or xs.max() > safe[2] or ys.min() < safe[1] or ys.max() > safe[3]:
                warnings.append(f"Lyric exceeds {platform} safe area: {cue.text[:40]}")
            estimated_lines = max(1, min(4, round((ys.max() - ys.min() + 1) / max(1, settings.font_size))))
            glyph_height = (ys.max() - ys.min() + 1) / estimated_lines
            if glyph_height < 20:
                warnings.append(f"Lyric text becomes too small on {platform}: {cue.text[:40]}")
    return list(dict.fromkeys(warnings))


def _audio_peak(path: Path) -> float | None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return None
    result = subprocess.run([ffmpeg, "-hide_banner", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"], capture_output=True, text=True, timeout=180, check=False)
    match = re.search(r"max_volume:\s*(-?[\d.]+) dB", result.stderr)
    return float(match.group(1)) if match else None
