from __future__ import annotations

import re
import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .text import repair_mojibake


@dataclass(frozen=True)
class AudioProfile:
    duration: float
    bpm: float
    beats: np.ndarray
    downbeats: np.ndarray = field(default_factory=lambda: np.empty(0, dtype=np.float32))
    sections: np.ndarray = field(default_factory=lambda: np.empty(0, dtype=np.float32))
    energy_times: np.ndarray = field(default_factory=lambda: np.empty(0, dtype=np.float32))
    energy: np.ndarray = field(default_factory=lambda: np.empty(0, dtype=np.float32))
    onsets: np.ndarray = field(default_factory=lambda: np.empty(0, dtype=np.float32))


@dataclass(frozen=True)
class LyricWord:
    text: str
    start: float
    end: float


@dataclass(frozen=True)
class LyricCue:
    start: float
    end: float
    text: str
    words: tuple[LyricWord, ...] = ()


def analyze_audio(path: Path) -> AudioProfile:
    import librosa

    samples, rate = librosa.load(path, sr=22050, mono=True)
    hop = 512
    onset_envelope = librosa.onset.onset_strength(y=samples, sr=rate, hop_length=hop)
    tempo, beat_frames = librosa.beat.beat_track(onset_envelope=onset_envelope, sr=rate, hop_length=hop, units="frames")
    beats = librosa.frames_to_time(beat_frames, sr=rate).astype(np.float32)
    bpm = float(np.asarray(tempo).reshape(-1)[0]) if np.size(tempo) else 0.0
    duration = float(librosa.get_duration(y=samples, sr=rate))

    rms = librosa.feature.rms(y=samples, hop_length=hop)[0]
    centroid = librosa.feature.spectral_centroid(y=samples, sr=rate, hop_length=hop)[0]
    frame_count = min(len(rms), len(onset_envelope), len(centroid))
    times = librosa.frames_to_time(np.arange(frame_count), sr=rate, hop_length=hop).astype(np.float32)
    energy = _normalize(rms[:frame_count])
    onsets = _normalize(onset_envelope[:frame_count])

    if beat_frames.size >= 4:
        safe_frames = np.clip(beat_frames, 0, max(0, len(onset_envelope) - 1))
        phase_scores = [float(np.mean(onset_envelope[safe_frames[phase::4]])) for phase in range(4)]
        phase = int(np.argmax(phase_scores))
        downbeats = beats[phase::4].astype(np.float32)
    else:
        downbeats = beats[::4].astype(np.float32)

    boundaries = [0.0]
    if beat_frames.size:
        safe_frames = np.clip(beat_frames, 0, max(0, frame_count - 1))
        beat_energy = energy[safe_frames]
        beat_centroid = _normalize(centroid[:frame_count])[safe_frames]
        for index in range(8, len(beats), 4):
            energy_change = abs(float(np.mean(beat_energy[max(0, index - 4):index])) - float(np.mean(beat_energy[index:min(len(beats), index + 4)])))
            tone_change = abs(float(np.mean(beat_centroid[max(0, index - 4):index])) - float(np.mean(beat_centroid[index:min(len(beats), index + 4)])))
            phrase_boundary = index % 32 == 0
            if phrase_boundary or energy_change + .55 * tone_change > .34:
                candidate = float(beats[index])
                if candidate - boundaries[-1] >= 3.0:
                    boundaries.append(candidate)
    if duration - boundaries[-1] >= 2.0:
        boundaries.append(duration)
    return AudioProfile(duration, bpm, beats, downbeats, np.asarray(boundaries, dtype=np.float32), times, energy.astype(np.float32), onsets.astype(np.float32))


def _normalize(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=np.float32)
    if not values.size:
        return values
    low, high = np.percentile(values, [5, 95])
    return np.clip((values - low) / max(1e-6, high - low), 0, 1).astype(np.float32)


_TIMESTAMP = re.compile(r"(?P<h>\d{2}):(?P<m>\d{2}):(?P<s>\d{2})[,.](?P<ms>\d{3})")


def _seconds(value: str) -> float:
    match = _TIMESTAMP.fullmatch(value.strip())
    if not match:
        raise ValueError(f"Invalid subtitle timestamp: {value}")
    data = {key: int(number) for key, number in match.groupdict().items()}
    return data["h"] * 3600 + data["m"] * 60 + data["s"] + data["ms"] / 1000


def load_lyrics(path: Path | None, duration: float) -> list[LyricCue]:
    if path is None or not path.exists():
        return []
    content = repair_mojibake(path.read_text(encoding="utf-8-sig", errors="replace")).strip()
    if path.suffix.lower() == ".srt":
        word_data: list[dict] = []
        word_path = path.with_suffix(".words.json")
        if word_path.exists():
            try:
                word_data = json.loads(word_path.read_text(encoding="utf-8")).get("cues", [])
            except (ValueError, OSError):
                word_data = []
        cues: list[LyricCue] = []
        for block in re.split(r"\r?\n\s*\r?\n", content):
            lines = [line.strip() for line in block.splitlines() if line.strip()]
            timing_index = next((i for i, line in enumerate(lines) if "-->" in line), -1)
            if timing_index < 0:
                continue
            start_raw, end_raw = lines[timing_index].split("-->", 1)
            text = " ".join(lines[timing_index + 1 :]).strip()
            if text:
                cue_index = len(cues)
                raw_words = word_data[cue_index].get("words", []) if cue_index < len(word_data) else []
                words = tuple(LyricWord(str(word["text"]), float(word["start"]), float(word["end"])) for word in raw_words if {"text", "start", "end"} <= word.keys())
                cues.append(LyricCue(_seconds(start_raw), _seconds(end_raw), text, words))
        return cues

    lines = [line.strip() for line in content.splitlines() if line.strip()]
    if not lines:
        return []
    slot = duration / len(lines)
    return [LyricCue(index * slot, min(duration, (index + 1) * slot), text) for index, text in enumerate(lines)]
