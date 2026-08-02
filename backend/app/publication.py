from __future__ import annotations

import json
import shutil
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from .renderer import _fon


def create_release_pack(root: Path, project_name: str, video_files: list[str], options: dict, analysis: dict, quality: dict) -> list[str]:
    output = root / "output"
    generated: list[str] = []
    cover = next((path for path in (root / "input").glob("cover.*") if path.is_file()), None)
    lyrics = next((path for path in (root / "input").glob("lyrics.srt") if path.is_file()), None)
    if cover:
        thumbnail = output / "youtube_thumbnail.jpg"
        _thumbnail(cover, thumbnail, project_name)
        generated.append(thumbnail.name)
    if lyrics:
        destination = output / "lyrics.srt"
        shutil.copy2(lyrics, destination)
        generated.append(destination.name)
    captions = output / "social_captions.txt"
    captions.write_text(_captions(project_name), encoding="utf-8")
    generated.append(captions.name)
    manifest = output / "release_manifest.json"
    manifest.write_text(json.dumps({"formatVersion": 1, "project": project_name, "createdAt": datetime.now(UTC).isoformat(), "videos": video_files, "options": options, "analysis": analysis, "quality": quality}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    generated.append(manifest.name)
    report = output / "quality_report.json"
    report.write_text(json.dumps(quality, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    generated.append(report.name)
    archive = output / "release_pack.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as package:
        for filename in video_files + generated:
            path = output / filename
            if path.exists():
                package.write(path, filename)
    generated.append(archive.name)
    return generated


def _thumbnail(cover: Path, destination: Path, title: str) -> None:
    with Image.open(cover) as source:
        image = ImageOps.fit(source.convert("RGB"), (1280, 720), method=Image.Resampling.LANCZOS)
    dark = Image.new("RGBA", image.size, (0, 0, 0, 110))
    image = Image.alpha_composite(image.convert("RGBA"), dark)
    draw = ImageDraw.Draw(image)
    font = _font(72, "Arial", True, False)
    safe_title = title.upper()[:60]
    box = draw.textbbox((0, 0), safe_title, font=font, stroke_width=3)
    x, y = (1280 - (box[2] - box[0])) // 2, 580 - (box[3] - box[1])
    draw.text((x, y), safe_title, font=font, fill="white", stroke_width=3, stroke_fill="#080810")
    image.convert("RGB").save(destination, quality=94, optimize=True)


def _captions(title: str) -> str:
    return f"""YOUTUBE\n{title} — Official Lyric Video\n\nTIKTOK / REELS / SHORTS\n{title} ✨ Full song available now.\n\nHASHTAGS\n#NewMusic #LyricVideo #IndependentArtist #MusicRelease\n"""
