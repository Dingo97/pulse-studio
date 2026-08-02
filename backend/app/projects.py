from __future__ import annotations

import re
import shutil
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from .config import settings


ALLOWED_AUDIO = {".wav", ".mp3", ".flac", ".m4a", ".aac", ".ogg"}
ALLOWED_IMAGES = {".png", ".jpg", ".jpeg", ".webp"}
ALLOWED_BACKGROUNDS = ALLOWED_IMAGES | {".mp4", ".mov", ".mkv", ".webm", ".m4v"}
ALLOWED_LYRICS = {".srt", ".txt"}


def safe_name(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._ -]+", "", value).strip(" .")
    return value[:100] or "untitled"


def create_project(name: str) -> tuple[str, Path]:
    project_id = uuid4().hex
    root = settings.projects_dir / project_id
    (root / "input").mkdir(parents=True)
    (root / "output").mkdir()
    (root / "project.name").write_text(safe_name(name), encoding="utf-8")
    return project_id, root


def project_root(project_id: str) -> Path:
    if not re.fullmatch(r"[a-f0-9]{32}", project_id):
        raise FileNotFoundError(project_id)
    root = settings.projects_dir / project_id
    if not root.exists():
        raise FileNotFoundError(project_id)
    return root


def save_upload(upload: UploadFile, destination: Path, extensions: set[str]) -> Path:
    suffix = Path(upload.filename or "").suffix.lower()
    if suffix not in extensions:
        raise ValueError(f"Unsupported file type: {suffix or 'unknown'}")
    target = destination.with_suffix(suffix)
    for previous in destination.parent.glob(f"{destination.name}.*"):
        if previous != target and previous.is_file():
            previous.unlink()
    limit = settings.max_upload_mb * 1024 * 1024
    written = 0
    try:
        with target.open("wb") as output:
            while chunk := upload.file.read(1024 * 1024):
                written += len(chunk)
                if written > limit:
                    raise ValueError(f"The uploaded file exceeds the {settings.max_upload_mb} MB limit.")
                output.write(chunk)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    if target.stat().st_size == 0:
        target.unlink(missing_ok=True)
        raise ValueError("The uploaded file is empty.")
    return target


def find_input(root: Path, stem: str) -> Path | None:
    paths = [path for path in (root / "input").glob(f"{stem}.*") if path.is_file()]
    if stem == "lyrics":
        paths.sort(key=lambda path: path.suffix.lower() != ".srt")
    return paths[0] if paths else None
