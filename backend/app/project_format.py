from __future__ import annotations

import json
import re
import shutil
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from .config import settings
from .database import repository
from .projects import safe_name


FORMAT_VERSION = 1
MAX_FILES = 50
MAX_MANIFEST = 2 * 1024 * 1024
SAFE_ASSET = re.compile(
    r"^input/(?:"
    r"song\.(?:wav|mp3|flac|m4a|aac|ogg)|"
    r"cover\.(?:png|jpg|jpeg|webp)|"
    r"language\.txt|lyrics\.(?:txt|srt)|lyrics\.(?:words|alignment)\.json|"
    r"background_\d{3}\.(?:png|jpg|jpeg|webp|mp4|mov|mkv|webm|m4v)"
    r")$",
    re.IGNORECASE,
)


def export_pulseproject(project_id: str, root: Path) -> Path:
    record = repository.get_project(project_id)
    destination = root / "output" / f"{safe_name(record['name'])}.pulseproject"
    manifest = {
        "$schema": "https://pulse-studio.dev/schemas/project-v1.json",
        "formatVersion": FORMAT_VERSION,
        "name": record["name"],
        "createdAt": datetime.now(UTC).isoformat(),
        "settings": record["settings"],
        "analysis": record["analysis"],
        "assets": sorted(relative for path in (root / "input").iterdir() if path.is_file() and SAFE_ASSET.fullmatch(relative := f"input/{path.name}")),
    }
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        archive.writestr("pulseproject.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        for relative in manifest["assets"]:
            archive.write(root / relative, relative)
    return destination


def import_pulseproject(source: Path) -> tuple[str, str]:
    with zipfile.ZipFile(source) as archive:
        entries = archive.infolist()
        max_uncompressed = settings.max_upload_mb * 1024 * 1024
        filenames = [item.filename for item in entries]
        if len(entries) > MAX_FILES or sum(item.file_size for item in entries) > max_uncompressed:
            raise ValueError("Pulse project exceeds the safe import limits.")
        if len(filenames) != len(set(filenames)):
            raise ValueError("The project archive contains duplicate entries.")
        if any(item.flag_bits & 0x1 for item in entries):
            raise ValueError("Encrypted project archives are not supported.")
        names = set(filenames)
        if "pulseproject.json" not in names:
            raise ValueError("Missing pulseproject.json manifest.")
        manifest_info = archive.getinfo("pulseproject.json")
        if manifest_info.file_size > MAX_MANIFEST:
            raise ValueError("The project manifest is too large.")
        manifest = json.loads(archive.read("pulseproject.json"))
        if manifest.get("formatVersion") != FORMAT_VERSION:
            raise ValueError("Unsupported Pulse project version.")
        assets = manifest.get("assets", [])
        if not isinstance(assets, list) or any(not SAFE_ASSET.fullmatch(str(name)) or name not in names for name in assets):
            raise ValueError("The project contains an unsafe or unsupported asset path.")
        expected = {"pulseproject.json", *map(str, assets)}
        if names != expected:
            raise ValueError("The project archive contains undeclared files.")
        project_id = uuid4().hex
        name = safe_name(str(manifest.get("name", "Imported project")))
        root = settings.projects_dir / project_id
        (root / "input").mkdir(parents=True)
        (root / "output").mkdir()
        try:
            for relative in assets:
                target = root / relative
                with archive.open(relative) as incoming, target.open("wb") as output:
                    shutil.copyfileobj(incoming, output)
            (root / "project.name").write_text(name, encoding="utf-8")
            repository.create_project(project_id, name)
            repository.update_project(project_id, settings=manifest.get("settings", {}), analysis=manifest.get("analysis", {}), status="ready")
        except Exception:
            shutil.rmtree(root, ignore_errors=True)
            raise
    return project_id, name
