from app.text import repair_mojibake


def test_repairs_windows_1252_mojibake() -> None:
    assert repair_mojibake("Allâ€™inizio cominciÃ², poi tornÃ².") == "All’inizio cominciò, poi tornò."


def test_keeps_valid_unicode_unchanged() -> None:
    text = "È già più chiaro: l’amore, però, non c’è."
    assert repair_mojibake(text) == text


def test_repairs_iso_8859_1_control_style_mojibake() -> None:
    assert repair_mojibake("All\xe2\x80\x99inizio, torn\xc3\xb2.") == "All’inizio, tornò."
