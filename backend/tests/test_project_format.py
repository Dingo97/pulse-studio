from app.project_format import SAFE_ASSET


def test_project_asset_paths_are_restricted() -> None:
    assert SAFE_ASSET.fullmatch("input/song.wav")
    assert SAFE_ASSET.fullmatch("input/background_001.mp4")
    assert SAFE_ASSET.fullmatch("input/language.txt")
    assert SAFE_ASSET.fullmatch("input/lyrics.srt")
    assert SAFE_ASSET.fullmatch("input/lyrics.words.json")
    assert SAFE_ASSET.fullmatch("input/lyrics.alignment.json")
    assert not SAFE_ASSET.fullmatch("input/vocals.demucs.wav")
    assert not SAFE_ASSET.fullmatch("input/song.exe")
    assert not SAFE_ASSET.fullmatch("input/background_001.html")
    assert not SAFE_ASSET.fullmatch("../secret.txt")
    assert not SAFE_ASSET.fullmatch("input/plugin.py")
