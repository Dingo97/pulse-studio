from __future__ import annotations


_MOJIBAKE_MARKERS = ("Ã", "Â", "â", "ð", "�")


def repair_mojibake(value: str) -> str:
    """Repair UTF-8 text accidentally decoded as Windows-1252/Latin-1."""
    current = value
    for _ in range(2):
        if not any(marker in current for marker in _MOJIBAKE_MARKERS):
            break
        candidates = []
        for encoding in ("cp1252", "latin-1"):
            try:
                candidates.append(current.encode(encoding).decode("utf-8"))
            except (UnicodeEncodeError, UnicodeDecodeError):
                continue
        if not candidates:
            break
        candidate = min(candidates, key=_badness)
        if _badness(candidate) >= _badness(current):
            break
        current = candidate
    return current


def _badness(value: str) -> int:
    controls = sum(1 for char in value if "\x80" <= char <= "\x9f")
    return controls + sum(value.count(marker) for marker in _MOJIBAKE_MARKERS)
