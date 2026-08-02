from __future__ import annotations

import math
import os
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import cv2
import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from proglog import ProgressBarLogger

SYSTEM_FFMPEG = shutil.which("ffmpeg")
os.environ.setdefault("IMAGEIO_FFMPEG_EXE", SYSTEM_FFMPEG or imageio_ffmpeg.get_ffmpeg_exe())
os.environ.setdefault("FFMPEG_BINARY", os.environ["IMAGEIO_FFMPEG_EXE"])

from moviepy import AudioFileClip, VideoClip, VideoFileClip  # noqa: E402

from .media import AudioProfile, LyricCue
from .schemas import EditorSettings


@dataclass(frozen=True)
class RenderSpec:
    start: float
    duration: float
    width: int
    height: int
    fps: int
    quality: str
    encoder: str
    platform: str = "shorts"


class _WriteProgress(ProgressBarLogger):
    """Forwards MoviePy's frame-writing progress as a 0..1 fraction."""

    def __init__(self, callback: Callable[[float], None]) -> None:
        super().__init__()
        self._callback = callback

    def bars_callback(self, bar, attr, value, old_value=None) -> None:
        if attr != "index" or bar == "chunk":  # "chunk" is the short audio pass
            return
        total = self.bars[bar].get("total")
        if total:
            self._callback(min(1.0, value / total))


def nvenc_available() -> bool:
    try:
        result = subprocess.run(
            [os.environ["IMAGEIO_FFMPEG_EXE"], "-hide_banner", "-encoders"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        return "h264_nvenc" in result.stdout
    except (OSError, subprocess.SubprocessError):
        return False


def _font(size: int, family: str = "Arial", bold: bool = True, italic: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    key = family.casefold()
    linux_name = "DejaVuSans"
    windows_name = "arial"
    if "georgia" in key:
        linux_name, windows_name = "DejaVuSerif", "georgia"
    elif "courier" in key:
        linux_name, windows_name = "DejaVuSansMono", "cour"
    elif "impact" in key:
        linux_name, windows_name = "DejaVuSansCondensed", "impact"
    suffix = "-BoldOblique" if bold and italic else "-Bold" if bold else "-Oblique" if italic else ""
    win_suffix = "bi" if bold and italic else "bd" if bold else "i" if italic else ""
    font_root = Path(os.environ.get("APP_DATA_DIR", "data")) / "fonts"
    custom = next((path for path in font_root.glob("*") if path.suffix.lower() in {".ttf", ".otf"} and path.stem.casefold() == key), None) if font_root.exists() else None
    candidates = ([custom] if custom else []) + [
        Path(f"/usr/share/fonts/truetype/dejavu/{linux_name}{suffix}.ttf"),
        Path(f"C:/Windows/Fonts/{windows_name}{win_suffix}.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        Path("C:/Windows/Fonts/arialbd.ttf"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size)
    return ImageFont.load_default()


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if current and draw.textbbox((0, 0), candidate, font=font, stroke_width=2)[2] > max_width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def _safe_rect(width: int, height: int, platform: str) -> tuple[int, int, int, int]:
    profiles = {
        "youtube": (.05, .05, .05, .10),
        "shorts": (.055, .06, .10, .15),
        "reels": (.055, .06, .10, .16),
        "tiktok": (.055, .06, .11, .17),
        "none": (0.03, .03, .03, .03),
    }
    left, top, right, bottom = profiles.get(platform, profiles["shorts"] if height > width else profiles["youtube"])
    return int(width * left), int(height * top), int(width * (1 - right)), int(height * (1 - bottom))


@lru_cache(maxsize=512)
def lyric_card(text: str, active_word: int, width: int, height: int, landscape: bool, platform: str, settings_json: str) -> np.ndarray:
    settings = EditorSettings.model_validate_json(settings_json)
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    shadow_canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow_canvas)
    safe = _safe_rect(width, height, platform)
    requested = max(24, round(settings.font_size * height / (1080 if landscape else 1920)))
    max_width = int(min(safe[2] - safe[0], width * (0.43 if landscape else 0.84)))
    max_height = int((safe[3] - safe[1]) * (.58 if landscape else .42))
    size = requested
    while size > max(20, round(requested * .48)):
        font = _font(size, settings.font_family, settings.text_bold, settings.text_italic)
        layout_text = text if settings.word_animation == "ink" else text.upper()
        candidate_lines = _wrap(draw, layout_text, font, max_width)
        spacing = int(size * .22)
        candidate_height = len(candidate_lines) * int(size * 1.16) + max(0, len(candidate_lines) - 1) * spacing
        if len(candidate_lines) <= 4 and candidate_height <= max_height and all(draw.textbbox((0, 0), line, font=font)[2] <= max_width for line in candidate_lines):
            break
        size -= max(1, round(requested * .035))
    font = _font(size, settings.font_family, settings.text_bold, settings.text_italic)
    layout_text = text if settings.word_animation == "ink" else text.upper()
    lines = _wrap(draw, layout_text, font, max_width)[:4]
    spacing = int(size * 0.25)
    color_rgb = tuple(int(settings.text_color[i:i+2], 16) for i in (1, 3, 5))
    accent_rgb = tuple(int(settings.active_word_color[i:i+2], 16) for i in (1, 3, 5))
    shadow_rgb = tuple(int(settings.shadow_color[i:i+2], 16) for i in (1, 3, 5))
    shadow_alpha = round(255 * settings.shadow_opacity / 100)
    target_x = int(width * (settings.lyrics_x_landscape if landscape else settings.lyrics_x_vertical))
    target_y = int(height * (settings.lyrics_y_landscape if landscape else settings.lyrics_y_vertical))

    # Spatial lyric systems inspired by editorial kinetic typography. Their layouts are
    # deterministic, safe-area aware and intentionally distinct from the regular line renderer.
    if settings.word_animation in {"constellation", "impact"}:
        words = layout_text.split()
        if not words:
            return np.asarray(canvas)
        has_active_word = 0 <= active_word < len(words)
        active_word = min(max(active_word, 0), len(words) - 1)
        columns = 2 if settings.word_animation == "impact" else 3
        rows = math.ceil(len(words) / columns)
        cell_width = max_width / columns
        cell_height = min(size * 1.42, max_height / max(1, rows))
        block_height = cell_height * rows
        top = min(max(safe[1], target_y - block_height / 2), safe[3] - block_height)
        left = min(max(safe[0], target_x - max_width / 2), safe[2] - max_width)
        constellation_offsets = ((-.10, -.25), (.06, .18), (-.04, -.08), (.08, .22), (-.06, -.18), (.02, .06))
        for index, word in enumerate(words):
            row, column = divmod(index, columns)
            is_active = has_active_word and index == active_word
            is_sung = has_active_word and index < active_word
            if settings.word_animation == "impact":
                scale = 1.34 if is_active else (1.02 if index % 5 == 4 else .76 if index % 4 else .9)
                alpha = 255 if is_active else 150 if is_sung else 48
                offset_x, offset_y = (0, 0)
            else:
                scale = 1.08 if is_active else (.68 + (index % 3) * .09)
                alpha = 255 if is_active else 150 if is_sung else 66
                offset_x, offset_y = constellation_offsets[index % len(constellation_offsets)]
            word_font = _font(max(14, round(size * scale)), settings.font_family, settings.text_bold, settings.text_italic)
            box = draw.textbbox((0, 0), word, font=word_font, stroke_width=max(1, size // 22))
            word_width, word_height = box[2] - box[0], box[3] - box[1]
            if word_width > cell_width * .88:
                fitted_size = max(14, round(getattr(word_font, "size", size) * cell_width * .88 / word_width))
                word_font = _font(fitted_size, settings.font_family, settings.text_bold, settings.text_italic)
                box = draw.textbbox((0, 0), word, font=word_font, stroke_width=max(1, size // 22))
                word_width, word_height = box[2] - box[0], box[3] - box[1]
            center_x = left + (column + .5 + offset_x) * cell_width
            center_y = top + (row + .5 + offset_y) * cell_height
            x = min(max(safe[0], center_x - word_width / 2), safe[2] - word_width)
            y = min(max(safe[1], center_y - word_height / 2), safe[3] - word_height)
            fill_rgb = accent_rgb if is_active else color_rgb
            fill = fill_rgb + (alpha,)
            shadow = shadow_rgb + (round(shadow_alpha * alpha / 255),)
            shadow_draw.text((x + settings.shadow_distance, y + settings.shadow_distance), word, font=word_font, fill=shadow, stroke_width=max(1, size // 25), stroke_fill=shadow)
            draw.text((x, y), word, font=word_font, fill=fill, stroke_width=max(1, size // 20), stroke_fill=(3, 5, 14, min(220, alpha)))
        if settings.shadow_opacity and settings.shadow_blur:
            shadow_canvas = shadow_canvas.filter(ImageFilter.GaussianBlur(radius=max(.1, settings.shadow_blur * height / (1080 if landscape else 1920))))
        return np.asarray(Image.alpha_composite(shadow_canvas, canvas))

    boxes = [draw.textbbox((0, 0), line, font=font, stroke_width=max(2, size // 18)) for line in lines]
    block_height = sum(box[3] - box[1] for box in boxes) + spacing * max(0, len(lines) - 1)
    y = min(max(safe[1], target_y - block_height // 2), safe[3] - block_height)
    line_widths = [box[2] - box[0] for box in boxes]
    block_width = max(line_widths, default=0)
    block_left = min(max(safe[0], target_x - block_width // 2), safe[2] - block_width)
    word_cursor = 0
    for line, box in zip(lines, boxes):
        line_width = box[2] - box[0]
        if settings.text_align == "right":
            x = block_left + block_width - line_width
        elif settings.text_align == "left":
            x = block_left
        else:
            x = block_left + (block_width - line_width) // 2
        cursor_x = x
        line_words = line.split()
        for local_index, word in enumerate(line_words):
            global_index = word_cursor + local_index
            fill = (accent_rgb if settings.word_animation != "none" and global_index == active_word else color_rgb) + (255,)
            if settings.word_animation == "karaoke" and global_index < active_word:
                fill = accent_rgb + (255,)
            draw_y = y
            word_shadow_alpha = shadow_alpha
            if settings.word_animation == "ink":
                if global_index > active_word:
                    fill = color_rgb + (0,)
                    word_shadow_alpha = 0
                elif global_index < active_word:
                    fill = color_rgb + (235,)
                draw_y += round(size * (-.06 if global_index % 2 else .04))
            shadow = shadow_rgb + (word_shadow_alpha,)
            shadow_draw.text((cursor_x + settings.shadow_distance, draw_y + settings.shadow_distance), word, font=font, fill=shadow, stroke_width=max(1, size // 22), stroke_fill=shadow)
            draw.text((cursor_x, draw_y), word, font=font, fill=fill, stroke_width=max(2, size // 18), stroke_fill=(3, 5, 14, min(235, fill[3])))
            cursor_x += draw.textlength(word + (" " if local_index < len(line_words) - 1 else ""), font=font)
        word_cursor += len(line_words)
        y += box[3] - box[1] + spacing
    if settings.shadow_opacity and settings.shadow_blur:
        shadow_canvas = shadow_canvas.filter(ImageFilter.GaussianBlur(radius=max(.1, settings.shadow_blur * height / (1080 if landscape else 1920))))
    return np.asarray(Image.alpha_composite(shadow_canvas, canvas))


class PulseRenderer:
    def __init__(self, audio: Path, cover: Path, lyrics: list[LyricCue], profile: AudioProfile, settings: EditorSettings, backgrounds: list[Path] | None = None) -> None:
        self.audio = audio
        self.cover = cover
        self.lyrics = lyrics
        self.profile = profile
        self.settings = settings
        self.backgrounds = backgrounds or []
        self._stable_crop_positions: dict[tuple[int, int, int, int], tuple[float, float]] = {}
        self._background_images: dict[Path, np.ndarray] = {}
        for path in self.backgrounds:
            if path.suffix.lower() not in {".mp4", ".mov", ".mkv", ".webm", ".m4v"}:
                frame = cv2.imread(str(path), cv2.IMREAD_COLOR)
                if frame is not None:
                    self._background_images[path] = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        cover_bgr = cv2.imread(str(cover), cv2.IMREAD_COLOR)
        if cover_bgr is None:
            raise ValueError("The cover image could not be decoded.")
        self._cover_rgb = cv2.cvtColor(cover_bgr, cv2.COLOR_BGR2RGB)

    def render(self, target: Path, spec: RenderSpec, on_progress: Callable[[float], None] | None = None) -> None:
        audio_source = AudioFileClip(str(self.audio))
        # librosa and ffmpeg can disagree on the song length by a few ms; trust the shorter one.
        song_end = min(self.profile.duration, float(audio_source.duration))
        duration = min(spec.duration, max(0.0, song_end - spec.start - 0.05))
        if duration < 0.5:
            audio_source.close()
            raise ValueError("The selected range is outside the song.")
        video_backgrounds = {path: VideoFileClip(str(path), audio=False) for path in self.backgrounds if path.suffix.lower() in {".mp4", ".mov", ".mkv", ".webm", ".m4v"}}
        dynamic_background = self.settings.background_mode == "custom" and bool(self.backgrounds)
        base = None if dynamic_background else self._base_frame(spec.width, spec.height, platform=self._platform(spec), include_cover=False)
        landscape = spec.width > spec.height

        def frame(t: float) -> np.ndarray:
            absolute = spec.start + t
            pulse = self._pulse(absolute)
            strong = self._strong_pulse(absolute)
            background_scale = 1.0 + 0.012 * math.sin(t * 0.42)
            cover_scale = 1.0 + (0.025 * pulse + .025 * strong if self.settings.visualizer_pulse else 0.0)
            current_base = base
            if dynamic_background:
                source = self._background_source(absolute, video_backgrounds)
                current_base = self._base_frame(spec.width, spec.height, source, self._platform(spec), include_cover=False)
            assert current_base is not None
            rendered = self._zoom(current_base, background_scale, spec.width, spec.height)
            rendered = self._composite_cover(rendered, spec.width, spec.height, self._platform(spec), cover_scale)
            if pulse > 0.3:
                rendered = self._chromatic(rendered, int(1 + pulse * 4))
            if self.settings.visualizer_enabled and self.settings.visualizer != "none":
                rendered = self._visualizer(rendered, absolute, pulse, self._platform(spec))
            cue = next((cue for cue in self.lyrics if cue.start <= absolute < cue.end), None)
            if cue:
                age = max(0.0, absolute - cue.start)
                reveal = min(1.0, age / 0.42)
                display_text = cue.text
                if self.settings.animation == "typewriter":
                    display_text = cue.text[:max(1, round(len(cue.text) * min(1.0, age / max(.5, cue.end - cue.start))))]
                words = display_text.split()
                if cue.words and self.settings.animation != "typewriter":
                    active_word = next((index for index, word in enumerate(cue.words) if word.start <= absolute < word.end), -1)
                else:
                    active_word = min(max(0, len(words) - 1), int((absolute - cue.start) / max(.01, cue.end - cue.start) * max(1, len(words))))
                overlay = lyric_card(display_text, active_word, spec.width, spec.height, landscape, self._platform(spec), self.settings.model_dump_json()).copy()
                if self.settings.word_animation in {"pop", "bounce"} and words:
                    phase = ((absolute - cue.start) / max(.01, cue.end - cue.start) * len(words)) % 1
                    word_pulse = math.exp(-phase * 8)
                    if self.settings.word_animation == "bounce":
                        overlay = cv2.warpAffine(overlay, np.float32([[1, 0, 0], [0, 1, -round(word_pulse * spec.height * .012)]]), (spec.width, spec.height))
                if self.settings.animation == "fade":
                    overlay[:, :, 3] = (overlay[:, :, 3].astype(np.float32) * reveal).astype(np.uint8)
                elif self.settings.animation == "blur" and reveal < 1:
                    overlay = cv2.GaussianBlur(overlay, (0, 0), sigmaX=max(.1, 10 * (1 - reveal)))
                elif self.settings.animation == "pop" and reveal < 1:
                    scale_in = .78 + .22 * (1 - (1 - reveal) ** 3)
                    matrix = cv2.getRotationMatrix2D((spec.width / 2, spec.height / 2), 0, scale_in)
                    overlay = cv2.warpAffine(overlay, matrix, (spec.width, spec.height), borderMode=cv2.BORDER_CONSTANT)
                distance = round((1 - reveal) * min(spec.width, spec.height) * .045)
                dx = -distance if self.settings.animation_direction == "right" else distance if self.settings.animation_direction == "left" else 0
                dy = -distance if self.settings.animation_direction == "down" else distance if self.settings.animation_direction == "up" else 0
                if dx or dy:
                    overlay = cv2.warpAffine(overlay, np.float32([[1, 0, dx], [0, 1, dy]]), (spec.width, spec.height), borderMode=cv2.BORDER_CONSTANT)
                alpha = overlay[:, :, 3:4].astype(np.float32) / 255.0
                rendered = (overlay[:, :, :3] * alpha + rendered * (1 - alpha)).astype(np.uint8)
            return self._finish(rendered, absolute)

        video = VideoClip(frame_function=frame, duration=duration)
        final = None
        try:
            audio_clip = audio_source.subclipped(spec.start, spec.start + duration)
            final = video.with_audio(audio_clip)
            use_nvenc = spec.encoder == "nvenc" or (spec.encoder == "auto" and nvenc_available())
            codec = "h264_nvenc" if use_nvenc else "libx264"
            bitrate = {"balanced": "8M", "high": "12M", "max": "18M"}[spec.quality]
            params = ["-pix_fmt", "yuv420p", "-movflags", "+faststart"]
            if use_nvenc:
                params += ["-preset", "p5", "-rc", "vbr", "-cq", "19"]
            target.parent.mkdir(parents=True, exist_ok=True)
            final.write_videofile(
                str(target), fps=spec.fps, codec=codec, audio_codec="aac",
                bitrate=bitrate, audio_bitrate="320k", ffmpeg_params=params,
                temp_audiofile=str(target.with_suffix(".audio.m4a")), remove_temp=True,
                logger=_WriteProgress(on_progress) if on_progress else None,
            )
        finally:
            if final is not None:
                final.close()
            video.close()
            audio_source.close()
            for background_clip in video_backgrounds.values():
                background_clip.close()

    def _base_frame(self, width: int, height: int, custom_source: np.ndarray | None = None, platform: str = "shorts", include_cover: bool = True) -> np.ndarray:
        cover = self._cover_rgb
        source = cover
        if custom_source is not None:
            source = custom_source[:, :, :3].astype(np.uint8)
        if self.settings.background_mode == "solid":
            rgb = tuple(int(self.settings.background_color[i:i+2], 16) for i in (1, 3, 5))
            bg = np.full((height, width, 3), rgb, dtype=np.uint8)
        else:
            if self.settings.smart_crop and not self.settings.section_cuts:
                bg = self._stable_crop_fill(source, width, height)
            else:
                bg = self._crop_fill(source, width, height, self.settings.smart_crop)
            if self.settings.background_saturation != 100:
                hsv = cv2.cvtColor(bg, cv2.COLOR_RGB2HSV).astype(np.float32)
                hsv[:, :, 1] *= self.settings.background_saturation / 100
                bg = cv2.cvtColor(np.clip(hsv, 0, 255).astype(np.uint8), cv2.COLOR_HSV2RGB)
            if self.settings.background_brightness != 100:
                bg = np.clip(bg.astype(np.float32) * self.settings.background_brightness / 100, 0, 255).astype(np.uint8)
            if self.settings.background_blur:
                bg = cv2.GaussianBlur(bg, (0, 0), sigmaX=self.settings.background_blur)
            bg = (bg.astype(np.float32) * 0.52).astype(np.uint8)
        if not include_cover or not self.settings.cover_enabled:
            return bg
        return self._composite_cover(bg, width, height, platform)

    def _composite_cover(self, frame: np.ndarray, width: int, height: int, platform: str, scale: float = 1.0) -> np.ndarray:
        if not self.settings.cover_enabled:
            return frame
        bg = frame.copy()
        base_side = min(width * 0.68, height * 0.48)
        side = int(base_side * scale)
        art = cv2.resize(self._cover_rgb, (side, side), interpolation=cv2.INTER_LANCZOS4)
        safe = _safe_rect(width, height, platform)
        ax = int(width * (0.27 if width > height else 0.5) - side / 2)
        ay = int(height * (0.5 if width > height else 0.31) - side / 2)
        ax = min(max(safe[0], ax), safe[2] - side)
        ay = min(max(safe[1], ay), safe[3] - side)
        if self.settings.cover_shadow:
            shadow = np.zeros_like(bg)
            cv2.rectangle(shadow, (ax + 12, ay + 18), (ax + side + 12, ay + side + 18), (0, 0, 0), -1)
            shadow = cv2.GaussianBlur(shadow, (0, 0), 22)
            bg = cv2.addWeighted(bg, 1.0, shadow, 0.5, 0)
        bg[ay:ay + side, ax:ax + side] = art
        return bg

    def _visualizer(self, frame: np.ndarray, absolute: float, pulse: float, platform: str = "auto") -> np.ndarray:
        out = frame.copy()
        pulse = pulse if self.settings.visualizer_pulse else 0.0
        height, width = out.shape[:2]
        color = tuple(int(self.settings.visualizer_color[i:i+2], 16) for i in (5, 3, 1))
        landscape = width > height
        center_x = int(width * (self.settings.visualizer_x_landscape if landscape else self.settings.visualizer_x_vertical))
        center_y = int(height * (self.settings.visualizer_y_landscape if landscape else self.settings.visualizer_y_vertical))
        safe = _safe_rect(width, height, ("youtube" if landscape else "tiktok") if platform == "auto" else platform)
        if self.settings.visualizer == "ring":
            radius = int(min(width, height) * (.16 + .025 * pulse))
            center_x = min(max(safe[0] + radius, center_x), safe[2] - radius)
            center_y = min(max(safe[1] + radius, center_y), safe[3] - radius)
            cv2.circle(out, (center_x, center_y), radius, color, max(2, width // 360), cv2.LINE_AA)
        else:
            count = 36
            half_width = int(width * (.175 if landscape else .34))
            center_x = min(max(safe[0] + half_width, center_x), safe[2] - half_width)
            center_y = min(max(safe[1] + int(height * .07), center_y), safe[3] - int(height * .07))
            for index in range(count):
                phase = absolute * 4.2 + index * .63
                level = .18 + .55 * abs(math.sin(phase)) * (.45 + .55 * pulse)
                x = int(center_x - half_width + index * half_width * 2 / (count - 1))
                length = int(height * .07 * level)
                if self.settings.visualizer == "wave":
                    cv2.circle(out, (x, center_y + int(math.sin(phase) * length)), max(1, width // 420), color, -1, cv2.LINE_AA)
                else:
                    cv2.line(out, (x, center_y - length), (x, center_y + length), color, max(2, width // 430), cv2.LINE_AA)
        return out

    def _pulse(self, absolute: float) -> float:
        if self.profile.beats.size == 0:
            return 0.0
        index = int(np.searchsorted(self.profile.beats, absolute))
        candidates = self.profile.beats[max(0, index - 1):min(len(self.profile.beats), index + 1)]
        distance = min((abs(float(beat) - absolute) for beat in candidates), default=1.0)
        return math.exp(-distance * 18.0)

    def _strong_pulse(self, absolute: float) -> float:
        if self.profile.downbeats.size == 0:
            return 0.0
        index = int(np.searchsorted(self.profile.downbeats, absolute))
        candidates = self.profile.downbeats[max(0, index - 1):min(len(self.profile.downbeats), index + 1)]
        distance = min((abs(float(beat) - absolute) for beat in candidates), default=1.0)
        return math.exp(-distance * 13.0)

    def _platform(self, spec: RenderSpec) -> str:
        return spec.platform if self.settings.safe_area == "auto" else self.settings.safe_area

    def _loop_time(self, absolute: float, source_duration: float) -> float:
        if source_duration <= .05:
            return 0.0
        local = absolute
        section_index = 0
        if self.settings.section_cuts and self.profile.sections.size:
            section_index = max(0, int(np.searchsorted(self.profile.sections, absolute, side="right") - 1))
            local = absolute - float(self.profile.sections[section_index]) + (section_index * source_duration * .381966)
        local = (max(0.0, local) + self.settings.background_video_offset) * self.settings.background_video_speed
        if self.settings.background_loop == "freeze":
            return min(source_duration - .02, max(0.0, local))
        if self.settings.background_loop == "pingpong":
            cycle = local % (source_duration * 2)
            return min(source_duration - .02, cycle if cycle <= source_duration else source_duration * 2 - cycle)
        return min(source_duration - .02, local % source_duration)

    def _background_source(self, absolute: float, video_backgrounds: dict[Path, VideoFileClip]) -> np.ndarray:
        section_index = max(0, int(np.searchsorted(self.profile.sections, absolute, side="right") - 1)) if self.settings.section_cuts and self.profile.sections.size else 0
        path = self.backgrounds[section_index % len(self.backgrounds)]
        if path in video_backgrounds:
            clip = video_backgrounds[path]
            return clip.get_frame(self._loop_time(absolute, float(clip.duration)))[:, :, :3].astype(np.uint8)
        return self._background_images.get(path, self._cover_rgb)

    @staticmethod
    def _crop_fill(source: np.ndarray, width: int, height: int, smart: bool) -> np.ndarray:
        resized, x, y, _, _ = PulseRenderer._crop_geometry(source, width, height, smart)
        return resized[y:y + height, x:x + width]

    def _stable_crop_fill(self, source: np.ndarray, width: int, height: int) -> np.ndarray:
        resized, suggested_x, suggested_y, max_x, max_y = self._crop_geometry(source, width, height, True)
        key = (source.shape[1], source.shape[0], width, height)
        if key not in self._stable_crop_positions:
            self._stable_crop_positions[key] = (
                suggested_x / max_x if max_x else .5,
                suggested_y / max_y if max_y else .5,
            )
        normalized_x, normalized_y = self._stable_crop_positions[key]
        x = min(max_x, max(0, round(normalized_x * max_x)))
        y = min(max_y, max(0, round(normalized_y * max_y)))
        return resized[y:y + height, x:x + width]

    @staticmethod
    def _crop_geometry(source: np.ndarray, width: int, height: int, smart: bool) -> tuple[np.ndarray, int, int, int, int]:
        scale = max(width / source.shape[1], height / source.shape[0])
        resized = cv2.resize(source, None, fx=scale, fy=scale, interpolation=cv2.INTER_LANCZOS4)
        max_x, max_y = max(0, resized.shape[1] - width), max(0, resized.shape[0] - height)
        x, y = max_x // 2, max_y // 2
        if smart and (max_x > 4 or max_y > 4):
            analysis_scale = min(1.0, 360.0 / max(resized.shape[:2]))
            analysis = cv2.resize(resized, None, fx=analysis_scale, fy=analysis_scale, interpolation=cv2.INTER_AREA)
            gray = cv2.cvtColor(analysis, cv2.COLOR_RGB2GRAY)
            saliency = cv2.GaussianBlur(np.abs(cv2.Laplacian(gray, cv2.CV_32F)), (0, 0), 3)
            small_width, small_height = max(1, round(width * analysis_scale)), max(1, round(height * analysis_scale))
            small_max_x, small_max_y = max(0, analysis.shape[1] - small_width), max(0, analysis.shape[0] - small_height)
            candidates = 9
            best_score = -1.0
            for index in range(candidates):
                cx = round(small_max_x * index / (candidates - 1)) if small_max_x else 0
                cy = round(small_max_y * index / (candidates - 1)) if small_max_y else 0
                if max_x:
                    score = float(np.mean(saliency[:, cx:cx + small_width])) - .04 * abs(index / (candidates - 1) - .5)
                    if score > best_score:
                        best_score, x = score, round(cx / analysis_scale)
                else:
                    score = float(np.mean(saliency[cy:cy + small_height, :])) - .04 * abs(index / (candidates - 1) - .5)
                    if score > best_score:
                        best_score, y = score, round(cy / analysis_scale)
        return resized, x, y, max_x, max_y

    @staticmethod
    def _zoom(frame: np.ndarray, scale: float, width: int, height: int) -> np.ndarray:
        # The pulse formula can dip below 1.0; never resize under the target or the crop breaks.
        new_width = max(width, round(frame.shape[1] * scale))
        new_height = max(height, round(frame.shape[0] * scale))
        resized = cv2.resize(frame, (new_width, new_height), interpolation=cv2.INTER_LINEAR)
        x = (new_width - width) // 2
        y = (new_height - height) // 2
        return resized[y:y + height, x:x + width]

    @staticmethod
    def _chromatic(frame: np.ndarray, amount: int) -> np.ndarray:
        result = frame.copy()
        result[:, amount:, 0] = frame[:, :-amount, 0]
        result[:, :-amount, 2] = frame[:, amount:, 2]
        return result

    def _finish(self, frame: np.ndarray, absolute: float) -> np.ndarray:
        height, width = frame.shape[:2]
        result = frame.astype(np.float32)
        # Perceptual response: low UI values must stay genuinely subtle.  Linear
        # opacity made every procedural effect look like a filter pasted on top.
        intensity = (self.settings.overlay_intensity / 100) ** 1.28
        if self.settings.overlay == "vignette" and intensity:
            yy, xx = np.ogrid[:height, :width]
            radius = np.sqrt(((xx - width / 2) / width) ** 2 + ((yy - height / 2) / height) ** 2)
            vignette = np.clip(1.04 - radius * (0.35 + .65 * intensity), 0.58, 1.0)[:, :, None]
            result *= vignette
        elif self.settings.overlay == "grain" and intensity:
            rng = np.random.default_rng(round(absolute * 12))
            small_h, small_w = max(90, height // 5), max(90, width // 5)
            noise = rng.normal(0, 1, (small_h, small_w)).astype(np.float32)
            fine = cv2.resize(noise, (width, height), interpolation=cv2.INTER_NEAREST)[:, :, None]
            exposure = math.sin(absolute * 7.1) * .22 + math.sin(absolute * 3.7) * .12
            result += fine * (4.2 * intensity) + exposure * intensity
        elif self.settings.overlay == "dust" and intensity:
            rng = np.random.default_rng(round(absolute * 3))
            dust = np.zeros_like(result)
            for _ in range(max(2, round(22 * intensity))):
                radius = int(rng.integers(1, max(2, round(min(width, height) * .0025))))
                cv2.circle(dust, (int(rng.integers(0, width)), int(rng.integers(0, height))), radius, (205, 200, 184), -1, cv2.LINE_AA)
            result += cv2.GaussianBlur(dust, (0, 0), 1.4) * .18
        elif self.settings.overlay == "scratches" and intensity:
            cycle = 6.5
            phase = (absolute / cycle + .17) % 1
            transient = max(0.0, min(1.0, (phase - .02) / .06)) * max(0.0, min(1.0, (.31 - phase) / .11))
            # A nearly invisible base prevents hard on/off cuts; the pronounced
            # scratch still appears only during the short transient envelope.
            envelope = .08 + .92 * transient
            rng = np.random.default_rng(math.floor(absolute / cycle) + 904)
            scratches = np.zeros_like(result)
            for _ in range(max(1, round(3 * intensity))):
                x = int(rng.integers(0, width))
                lean = int(rng.integers(-3, 4))
                shade = float(rng.integers(150, 220))
                cv2.line(scratches, (x, int(height * .03)), (x + lean, int(height * .97)), (shade, shade, shade), max(1, width // 1400), cv2.LINE_AA)
            result += cv2.GaussianBlur(scratches, (0, 0), .45) * intensity * envelope * .24
        elif self.settings.overlay in {"light_leaks", "film_burn"} and intensity:
            beat = self._pulse(absolute)
            small_w, small_h = max(64, width // 8), max(64, height // 8)
            glow = np.zeros((small_h, small_w, 3), dtype=np.float32)
            drift = math.sin(absolute * .72)
            if self.settings.overlay == "light_leaks":
                cv2.ellipse(glow, (round(small_w * (-.12 + .035 * drift)), round(small_h * (.35 + .06 * math.sin(absolute * .13)))), (round(small_w * .22), round(small_h * .58)), -7, 0, 360, (255, 65, 16), -1)
                cv2.ellipse(glow, (round(small_w * (1.12 - .025 * drift)), round(small_h * (.7 + .05 * math.cos(absolute * .17)))), (round(small_w * .2), round(small_h * .5)), 9, 0, 360, (255, 32, 102), -1)
                alpha = intensity * (.22 + .035 * beat)
            else:
                event_phase = (absolute / 9.7 + .11) % 1
                rise = max(0.0, min(1.0, (event_phase - .02) / .06))
                fall = max(0.0, min(1.0, (.34 - event_phase) / .15))
                event = rise * fall
                edge = 0 if math.floor(absolute / 9.7) % 2 == 0 else small_w - 1
                cv2.ellipse(glow, (edge, round(small_h * (.48 + .12 * drift))), (round(small_w * .28), round(small_h * .72)), 0, 0, 360, (255, 48, 0), -1)
                cv2.ellipse(glow, (edge, round(small_h * .55)), (round(small_w * .13), round(small_h * .38)), 0, 0, 360, (255, 178, 26), -1)
                alpha = intensity * event * .72
            glow = cv2.GaussianBlur(glow, (0, 0), max(7, min(small_w, small_h) * .18))
            glow = cv2.resize(glow, (width, height), interpolation=cv2.INTER_LINEAR)
            result = 255 - (255 - result) * (255 - np.clip(glow * alpha, 0, 255)) / 255
        elif self.settings.overlay == "rain" and intensity:
            rain = np.zeros_like(result)
            rng = np.random.default_rng(4471)
            for layer, count in ((0, 34), (1, 54)):
                speed = height * (.38 if layer == 0 else .72)
                for _ in range(max(2, round(count * intensity))):
                    base_x, base_y = float(rng.random()), float(rng.random())
                    length = round(height * rng.uniform(.018, .038 if layer == 0 else .065))
                    y = int((base_y * (height + length) + absolute * speed) % (height + length) - length)
                    x = int((base_x * width + y * .14) % (width + width * .12) - width * .06)
                    shade = 125 if layer == 0 else 170
                    cv2.line(rain, (x, y), (x + max(2, length // 5), y + length), (shade, shade + 18, shade + 26), max(1, width // (1500 if layer == 0 else 1000)), cv2.LINE_AA)
            result += cv2.GaussianBlur(rain, (0, 0), .65) * .22
        elif self.settings.overlay == "scanlines" and intensity:
            spacing = max(3, round(height / 360))
            phase = round(absolute * 18) % spacing
            result[phase::spacing] *= 1 - .18 * intensity
        elif self.settings.overlay == "vhs" and intensity:
            # Analog color bleed, interlaced scan and an occasional tracking tear.
            amount = max(1, round(min(width, height) * .0025 * intensity))
            result = self._chromatic(np.clip(result, 0, 255).astype(np.uint8), amount).astype(np.float32)
            gray = np.mean(result, axis=2, keepdims=True)
            result = result * (1 - .08 * intensity) + gray * (.08 * intensity)
            spacing = max(3, round(height / 300))
            phase = round(absolute * 18) % spacing
            result[phase::spacing] *= 1 - .12 * intensity
            result *= 1 + math.sin(absolute * 7.3) * .008 * intensity
            event_phase = (absolute / 3.7) % 1
            rise = max(0.0, min(1.0, (event_phase - .01) / .04))
            fall = max(0.0, min(1.0, (.20 - event_phase) / .09))
            tear = rise * fall
            if tear > .01:
                rng = np.random.default_rng(math.floor(absolute / 3.7) + 771)
                band_y = int(rng.uniform(.16, .84) * height)
                band_height = max(2, round(height * .018))
                shift = round(width * (.006 + .018 * tear) * intensity) * (-1 if rng.random() < .5 else 1)
                end = min(height, band_y + band_height)
                result[band_y:end] = np.roll(result[band_y:end], shift, axis=1)
                result[band_y:min(height, band_y + max(1, height // 540))] += 28 * tear * intensity
            roll_y = round(((absolute * .21) % 1) * height)
            band = max(1, round(height * .006))
            result[max(0, roll_y - band):min(height, roll_y + band)] += 5 * intensity
        elif self.settings.overlay == "bokeh" and intensity:
            small_w, small_h = max(64, width // 8), max(64, height // 8)
            lights = np.zeros((small_h, small_w, 3), dtype=np.float32)
            rng = np.random.default_rng(731)
            drift = absolute * .018
            colors = [(255, 196, 112), (112, 218, 255), (255, 105, 176), (255, 240, 170)]
            for index in range(12):
                x = int(((rng.random() + drift * (1 + index % 3)) % 1) * small_w)
                y = int(((rng.random() - drift * (.5 + index % 2)) % 1) * small_h)
                radius = max(2, round(min(small_w, small_h) * rng.uniform(.025, .075)))
                cv2.circle(lights, (x, y), radius, colors[index % len(colors)], -1, cv2.LINE_AA)
            lights = cv2.GaussianBlur(lights, (0, 0), max(2, min(small_w, small_h) * .025))
            lights = cv2.resize(lights, (width, height), interpolation=cv2.INTER_LINEAR)
            result = 255 - (255 - result) * (255 - np.clip(lights * intensity * .30, 0, 255)) / 255
        elif self.settings.overlay == "prism" and intensity:
            amount = max(1, round(min(width, height) * .0035 * intensity))
            result = self._chromatic(np.clip(result, 0, 255).astype(np.uint8), amount).astype(np.float32)
            prism = np.zeros_like(result)
            shift = round(math.sin(absolute * .45) * width * .06)
            points = np.array([[0, height], [max(0, width // 3 + shift), height // 3], [min(width - 1, width * 2 // 3 + shift), 0], [width // 3, height]], dtype=np.int32)
            cv2.fillConvexPoly(prism, points, (80, 178, 255), cv2.LINE_AA)
            prism = cv2.GaussianBlur(prism, (0, 0), max(5, min(width, height) * .04))
            result = 255 - (255 - result) * (255 - prism * intensity * .045) / 255
        return np.clip(result, 0, 255).astype(np.uint8)
