import numpy as np

from app.director import direct_song
from app.media import AudioProfile, LyricCue


def test_director_ranges_snap_to_downbeats() -> None:
    times = np.linspace(0, 120, 241, dtype=np.float32)
    energy = np.where((times >= 40) & (times <= 80), .9, .2).astype(np.float32)
    profile = AudioProfile(
        120, 120, np.arange(0, 120, .5, dtype=np.float32),
        np.arange(0, 120, 2, dtype=np.float32), np.asarray([0, 32, 64, 96, 120], dtype=np.float32),
        times, energy, energy,
    )
    lyrics = [LyricCue(40, 48, "we rise again"), LyricCue(56, 64, "we rise again")]
    plan = direct_song(profile, lyrics)
    downbeats = set(profile.downbeats.tolist())
    assert all(item["start"] in downbeats or item["output"] == "youtube" for item in plan["ranges"])
    assert plan["intensity"] == "high"
    assert plan["version"] == 2
    assert plan["signals"]["repeated_lines"] == 1
    assert all(0 <= item["score"] <= 1 for item in plan["ranges"])
