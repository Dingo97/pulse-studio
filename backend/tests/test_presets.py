import json
from pathlib import Path


def test_classic_preset_matches_schema_identity() -> None:
    root = Path(__file__).parents[2]
    preset = json.loads((root / "presets" / "classic-pulse.pulsepreset.json").read_text(encoding="utf-8"))
    schema = json.loads((root / "schemas" / "preset-v1.schema.json").read_text(encoding="utf-8"))
    assert preset["$schema"] == schema["$id"]
    assert preset["formatVersion"] == 1
    assert set(schema["properties"]["settings"]["required"]) == set(preset["settings"])
