from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

import numpy as np

from .media import AudioProfile, LyricCue


@dataclass(frozen=True)
class DirectedRange:
    output: str
    start: float
    duration: float
    score: float
    reason: str


def direct_song(profile: AudioProfile, lyrics: list[LyricCue]) -> dict:
    line_counts = Counter(_normalize(cue.text) for cue in lyrics if cue.text.strip())
    repeated_lines = sum(1 for count in line_counts.values() if count > 1)
    ranges = [
        _best_range("teaser", 15.0, profile, lyrics, line_counts, onset_weight=.60),
        _best_range("chorus", 30.0, profile, lyrics, line_counts, repeat_weight=.55),
        _best_range("lyrics", 45.0, profile, lyrics, line_counts, lyric_weight=.45),
        DirectedRange("youtube", 0.0, profile.duration, 1.0, "Full song"),
    ]
    mean_energy = float(np.mean(profile.energy)) if profile.energy.size else .5
    peak_energy = float(np.percentile(profile.energy, 90)) if profile.energy.size else .5
    intensity = "high" if peak_energy > .78 and mean_energy > .42 else "calm" if peak_energy < .55 else "balanced"
    return {
        "version": 2,
        "intensity": intensity,
        "effect_strength": {"calm": .45, "balanced": .72, "high": 1.0}[intensity],
        "method": "Downbeats + energy + transients + lyric repetition",
        "signals": {
            "sections": max(0, len(profile.sections) - 1),
            "downbeats": len(profile.downbeats),
            "lyric_lines": len(lyrics),
            "repeated_lines": repeated_lines,
        },
        "ranges": [item.__dict__ for item in ranges],
    }


def _best_range(
    output: str,
    duration: float,
    profile: AudioProfile,
    lyrics: list[LyricCue],
    counts: Counter[str],
    onset_weight: float = .30,
    repeat_weight: float = .25,
    lyric_weight: float = .25,
) -> DirectedRange:
    if profile.duration <= duration:
        return DirectedRange(output, 0.0, profile.duration, 1.0, "Song is shorter than target")
    candidates = profile.downbeats if profile.downbeats.size else profile.beats
    candidates = candidates[candidates <= profile.duration - duration]
    if not candidates.size:
        candidates = np.asarray([0.0])
    best = (float("-inf"), 0.0, "")
    for raw_start in candidates:
        start = float(raw_start)
        end = start + duration
        mask = (profile.energy_times >= start) & (profile.energy_times < end)
        energy = float(np.mean(profile.energy[mask])) if np.any(mask) else 0.0
        onset = float(np.mean(profile.onsets[mask])) if np.any(mask) else 0.0
        overlapping = [cue for cue in lyrics if cue.start < end and cue.end > start]
        lyric_coverage = min(1.0, sum(max(0.0, min(end, cue.end) - max(start, cue.start)) for cue in overlapping) / duration)
        repeat_score = min(1.0, sum(max(0, counts[_normalize(cue.text)] - 1) for cue in overlapping) / max(1, len(overlapping)))
        intro_penalty = .22 if start < min(8.0, profile.duration * .04) else 0.0
        outro_penalty = .18 if end > profile.duration - 5 else 0.0
        score = .48 * energy + onset_weight * onset + lyric_weight * lyric_coverage + repeat_weight * repeat_score - intro_penalty - outro_penalty
        if score > best[0]:
            reasons = ["high energy" if energy > .58 else "stable energy", "strong transients" if onset > .5 else "clean downbeat"]
            if repeat_score > .2:
                reasons.append("repeated lyric section")
            if lyric_coverage > .55:
                reasons.append("good lyric coverage")
            best = (score, start, ", ".join(reasons))
    # The old value was clipped directly even though the weighted terms can add
    # up well above 1.0. Normalising against the active weights makes the UI
    # confidence meaningful instead of reporting almost every choice as 100%.
    maximum = .48 + onset_weight + lyric_weight + repeat_weight
    confidence = max(0.0, min(1.0, best[0] / maximum))
    return DirectedRange(output, round(best[1], 3), min(duration, profile.duration - best[1]), round(confidence, 3), best[2])


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()
