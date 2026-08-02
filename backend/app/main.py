from __future__ import annotations

import shutil
import os
import mimetypes
import json
import zipfile
from uuid import uuid4
import subprocess
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import quote

import imageio_ffmpeg
from PIL import ImageFont
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from .config import settings
from .database import repository
from .director import direct_song
from .alignment import ALIGNMENT_VERSION, align_txt
from .jobs import render_queue
from .media import analyze_audio, load_lyrics
from .projects import (
    ALLOWED_AUDIO,
    ALLOWED_IMAGES,
    ALLOWED_BACKGROUNDS,
    ALLOWED_LYRICS,
    create_project,
    project_root,
    safe_name,
    save_upload,
    find_input,
)
from .project_format import export_pulseproject, import_pulseproject
from .renderer import nvenc_available
from .schemas import HealthView, JobView, LyricsUpdate, ProjectCreated, ProjectDetail, ProjectMetadata, ProjectRename, ProjectView, RenderRequest
from .text import repair_mojibake


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.projects_dir.mkdir(parents=True, exist_ok=True)
    (settings.data_dir / "fonts").mkdir(parents=True, exist_ok=True)
    repository.initialize()
    repository.recover_interrupted()
    yield


app = FastAPI(
    title="Pulse Studio API",
    version="0.1.0-alpha.1",
    description="Local-first GPU lyric video rendering API.",
    lifespan=lifespan,
)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["localhost", "127.0.0.1", "backend", "testserver"],
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def reject_cross_origin_writes(request: Request, call_next):
    """Block browser CSRF against this unauthenticated localhost API."""
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        origin = request.headers.get("origin")
        if origin and origin not in settings.allowed_origins:
            return JSONResponse(status_code=403, content={"detail": "Untrusted request origin."})
    return await call_next(request)


@app.get("/api/fonts")
def list_fonts() -> list[dict[str, str]]:
    root = settings.data_dir / "fonts"
    return [{"family": path.stem, "filename": path.name, "url": f"/api/fonts/{quote(path.name)}"} for path in sorted(root.iterdir()) if path.suffix.lower() in {".ttf", ".otf"}]


@app.post("/api/fonts")
async def upload_font(font: UploadFile = File(...)) -> dict[str, str]:
    suffix = Path(font.filename or "").suffix.lower()
    if suffix not in {".ttf", ".otf"}:
        raise HTTPException(status_code=415, detail="Only TTF and OTF fonts are supported.")
    family = safe_name(Path(font.filename or "Custom Font").stem)[:80]
    target = settings.data_dir / "fonts" / f"{family}{suffix}"
    limit = 15 * 1024 * 1024
    written = 0
    try:
        with target.open("wb") as output:
            while chunk := await font.read(1024 * 1024):
                written += len(chunk)
                if written > limit:
                    raise HTTPException(status_code=413, detail="The font must be smaller than 15 MB.")
                output.write(chunk)
        if not written:
            raise HTTPException(status_code=422, detail="The uploaded font is empty.")
        ImageFont.truetype(str(target), size=16)
    except HTTPException:
        target.unlink(missing_ok=True)
        raise
    except (OSError, ValueError) as exc:
        target.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail="The file is not a valid TrueType/OpenType font.") from exc
    return {"family": family, "filename": target.name, "url": f"/api/fonts/{quote(target.name)}"}


@app.get("/api/fonts/{filename}")
def get_font(filename: str) -> FileResponse:
    target = settings.data_dir / "fonts" / Path(filename).name
    if not target.is_file() or target.suffix.lower() not in {".ttf", ".otf"}:
        raise HTTPException(status_code=404, detail="Font not found")
    return FileResponse(target)


@app.get("/api/health", response_model=HealthView)
def health() -> HealthView:
    gpu = None
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=5, check=False,
        )
        gpu = result.stdout.strip().splitlines()[0] if result.returncode == 0 and result.stdout.strip() else None
    except (OSError, subprocess.SubprocessError):
        pass
    ffmpeg_path = os.environ.get("IMAGEIO_FFMPEG_EXE", imageio_ffmpeg.get_ffmpeg_exe())
    return HealthView(status="ok", ffmpeg=Path(ffmpeg_path).exists(), nvenc=nvenc_available(), gpu=gpu)


@app.post("/api/projects", response_model=ProjectCreated, status_code=201)
def upload_project(
    name: str = Form(..., min_length=1, max_length=100),
    language: str = Form(default="en", pattern="^(auto|en|it|es|fr|de|pt|nl|pl|tr|ru|ja|ko|zh)$"),
    song: UploadFile = File(...),
    cover: UploadFile = File(...),
    lyrics: UploadFile | None = File(default=None),
) -> ProjectCreated:
    project_id, root = create_project(name)
    try:
        save_upload(song, root / "input" / "song", ALLOWED_AUDIO)
        save_upload(cover, root / "input" / "cover", ALLOWED_IMAGES)
        if lyrics is not None and lyrics.filename:
            save_upload(lyrics, root / "input" / "lyrics", ALLOWED_LYRICS)
        (root / "input" / "language.txt").write_text(language, encoding="utf-8")
    except ValueError as exc:
        shutil.rmtree(root, ignore_errors=True)
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    repository.create_project(project_id, safe_name(name))
    return ProjectCreated(id=project_id, name=safe_name(name))


def _project_view(record: dict) -> dict:
    root = project_root(record["id"])
    analysis = record.get("analysis", {})
    return {
        **record,
        "has_song": find_input(root, "song") is not None,
        "has_cover": find_input(root, "cover") is not None,
        "has_lyrics": find_input(root, "lyrics") is not None,
        "outputs": sorted(path.name for path in (root / "output").glob("*.mp4")),
        "files": sorted(
            path.name for path in (root / "output").iterdir()
            if path.is_file() and not path.name.endswith(".audio.m4a") and ".partial" not in path.name
        ) if (root / "output").is_dir() else [],
        "duration": analysis.get("duration"),
        "bpm": analysis.get("bpm"),
    }


@app.get("/api/projects", response_model=list[ProjectView])
def list_projects() -> list[dict]:
    return [_project_view(record) for record in repository.list_projects()]


@app.get("/api/projects/{project_id}", response_model=ProjectDetail)
def get_project(project_id: str) -> dict:
    try:
        return _project_view(repository.get_project(project_id))
    except (KeyError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc


@app.patch("/api/projects/{project_id}", response_model=ProjectDetail)
def rename_project(project_id: str, request: ProjectRename) -> dict:
    try:
        name = safe_name(request.name)
        (project_root(project_id) / "project.name").write_text(name, encoding="utf-8")
        return _project_view(repository.update_project(project_id, name=name))
    except (KeyError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc


@app.post("/api/projects/{project_id}/duplicate", response_model=ProjectCreated, status_code=201)
def duplicate_project(project_id: str) -> ProjectCreated:
    try:
        source = project_root(project_id)
        record = repository.get_project(project_id)
    except (KeyError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc
    duplicate_id = uuid4().hex
    duplicate_name = safe_name(f"{record['name']} Copy")
    destination = settings.projects_dir / duplicate_id
    shutil.copytree(source, destination, ignore=shutil.ignore_patterns("output", "*.partial*", "*.audio.m4a"))
    (destination / "output").mkdir(exist_ok=True)
    (destination / "project.name").write_text(duplicate_name, encoding="utf-8")
    repository.create_project(duplicate_id, duplicate_name)
    repository.update_project(duplicate_id, settings=record["settings"], analysis=record["analysis"], status="draft")
    return ProjectCreated(id=duplicate_id, name=duplicate_name)


@app.delete("/api/projects/{project_id}")
def delete_project(project_id: str) -> dict[str, bool]:
    try:
        root = project_root(project_id)
        repository.delete_project(project_id)
        shutil.rmtree(root)
    except (KeyError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc
    return {"deleted": True}


@app.get("/api/projects/{project_id}/assets/{kind}")
def project_asset(project_id: str, kind: str) -> FileResponse:
    if kind not in {"song", "cover", "lyrics"}:
        raise HTTPException(status_code=404, detail="Asset not found")
    try:
        target = find_input(project_root(project_id), kind)
        if target is None:
            raise FileNotFoundError(kind)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Asset not found") from exc
    media = "audio/mpeg" if kind == "song" else "image/png" if kind == "cover" else "text/plain"
    return FileResponse(target, media_type=media, filename=target.name)


@app.get("/api/projects/{project_id}/files/{filename}")
def project_file(project_id: str, filename: str) -> FileResponse:
    if filename != Path(filename).name or filename.startswith("."):
        raise HTTPException(status_code=404, detail="File not found")
    try:
        output_root = (project_root(project_id) / "output").resolve()
        target = (output_root / filename).resolve()
        if target.parent != output_root:
            raise FileNotFoundError(filename)
        if not target.is_file():
            raise FileNotFoundError(filename)
    except (KeyError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail="File not found") from exc
    media_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    return FileResponse(target, media_type=media_type, filename=filename)


@app.get("/api/projects/{project_id}/export")
def export_project(project_id: str) -> FileResponse:
    try:
        root = project_root(project_id)
        archive = export_pulseproject(project_id, root)
    except (KeyError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc
    return FileResponse(archive, media_type="application/vnd.pulse.project+zip", filename=archive.name)


@app.post("/api/projects/import", response_model=ProjectCreated, status_code=201)
def import_project(project: UploadFile = File(...)) -> ProjectCreated:
    if not (project.filename or "").lower().endswith(".pulseproject"):
        raise HTTPException(status_code=415, detail="Choose a .pulseproject file")
    temporary = settings.data_dir / f".{uuid4().hex}.pulseproject"
    try:
        with temporary.open("wb") as output:
            written = 0
            limit = settings.max_upload_mb * 1024 * 1024
            while chunk := project.file.read(1024 * 1024):
                written += len(chunk)
                if written > limit:
                    raise HTTPException(status_code=413, detail=f"The project exceeds the {settings.max_upload_mb} MB upload limit.")
                output.write(chunk)
        project_id, name = import_pulseproject(temporary)
        return ProjectCreated(id=project_id, name=name)
    except (ValueError, zipfile.BadZipFile, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        temporary.unlink(missing_ok=True)


@app.post("/api/projects/{project_id}/prepare", response_model=ProjectMetadata)
def prepare_project(project_id: str) -> ProjectMetadata:
    try:
        root = project_root(project_id)
        song = find_input(root, "song")
        lyrics = find_input(root, "lyrics")
        if song is None:
            raise FileNotFoundError("song")
        cached = repository.get_project(project_id).get("analysis", {})
        language_path = root / "input" / "language.txt"
        language = language_path.read_text(encoding="utf-8").strip() if language_path.exists() else str(cached.get("language") or settings.whisper_language or "en")
        original_txt = root / "input" / "lyrics.txt"
        needs_alignment = original_txt.exists() and cached.get("alignment_version") != ALIGNMENT_VERSION
        if needs_alignment:
            lyrics = original_txt
        if cached.get("version") == 2 and not needs_alignment and cached.get("duration") and lyrics and lyrics.suffix.lower() == ".srt":
            cached_cues = load_lyrics(lyrics, float(cached["duration"]))
            return ProjectMetadata(
                duration=float(cached["duration"]), bpm=float(cached.get("bpm", 0)),
                lyrics=[{"start": cue.start, "end": cue.end, "text": cue.text, "words": [{"text": word.text, "start": word.start, "end": word.end} for word in cue.words]} for cue in cached_cues],
                lyrics_source=str(cached.get("lyrics_source", "srt")),
                downbeats=cached.get("downbeats", []), sections=cached.get("sections", []), director=cached.get("director", {}),
            )
        profile = analyze_audio(song)
        source = "none"
        if lyrics and lyrics.suffix.lower() == ".txt":
            aligned = root / "input" / "lyrics.srt"
            align_txt(song, lyrics, aligned, language)
            lyrics = aligned
            source = "aligned_txt"
        elif lyrics:
            source = "srt"
        cues = load_lyrics(lyrics, profile.duration)
        director = direct_song(profile, cues)
        analysis_payload = {
            "version": 2, "alignment_version": ALIGNMENT_VERSION, "language": language, "duration": profile.duration, "bpm": profile.bpm,
            "beats": profile.beats.tolist(), "downbeats": profile.downbeats.tolist(),
            "sections": profile.sections.tolist(), "director": director,
            "lyrics_source": source,
        }
        repository.update_project(project_id, analysis=analysis_payload, status="ready")
        return ProjectMetadata(
            duration=profile.duration, bpm=profile.bpm,
            lyrics=[{"start": cue.start, "end": cue.end, "text": cue.text, "words": [{"text": word.text, "start": word.start, "end": word.end} for word in cue.words]} for cue in cues],
            lyrics_source=source,
            downbeats=profile.downbeats.tolist(), sections=profile.sections.tolist(),
            director=director,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/projects/{project_id}/background")
def upload_background(project_id: str, background: list[UploadFile] = File(...)) -> dict:
    try:
        root = project_root(project_id)
        for previous in (root / "input").glob("background*.*"):
            previous.unlink(missing_ok=True)
        preview_root = root / "preview"
        shutil.rmtree(preview_root, ignore_errors=True)
        preview_root.mkdir(exist_ok=True)
        previews = []
        for index, upload in enumerate(background[:20]):
            source = save_upload(upload, root / "input" / f"background_{index:03d}", ALLOWED_BACKGROUNDS)
            preview_url = None
            if source.suffix.lower() in {".mp4", ".mov", ".mkv", ".webm", ".m4v"}:
                target = preview_root / f"background_{index:03d}.mp4"
                if _create_video_proxy(source, target):
                    preview_url = f"/api/projects/{project_id}/background-previews/{target.name}"
            previews.append({"index": index, "preview_url": preview_url})
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    return {"uploaded": min(20, len(background)), "previews": previews}


def _create_video_proxy(source: Path, target: Path) -> bool:
    """Create a small seekable browser proxy while preserving the original for export."""
    ffmpeg = shutil.which("ffmpeg") or imageio_ffmpeg.get_ffmpeg_exe()
    common = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(source),
        "-map", "0:v:0", "-an",
        "-vf", "scale=w='min(960,iw)':h='min(960,ih)':force_original_aspect_ratio=decrease:force_divisible_by=2",
        "-r", "24", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
    ]
    encoders = [
        ["-c:v", "h264_nvenc", "-preset", "p4", "-cq", "25", "-b:v", "0"],
        ["-c:v", "libx264", "-preset", "veryfast", "-crf", "27"],
    ] if nvenc_available() else [["-c:v", "libx264", "-preset", "veryfast", "-crf", "27"]]
    for encoder in encoders:
        partial = target.with_suffix(".partial.mp4")
        partial.unlink(missing_ok=True)
        try:
            result = subprocess.run([*common, *encoder, str(partial)], capture_output=True, text=True, timeout=900, check=False)
            if result.returncode == 0 and partial.is_file() and partial.stat().st_size > 0:
                partial.replace(target)
                return True
        except (OSError, subprocess.SubprocessError):
            pass
        finally:
            partial.unlink(missing_ok=True)
    return False


@app.get("/api/projects/{project_id}/background-previews/{filename}")
def background_preview(project_id: str, filename: str) -> FileResponse:
    if filename != Path(filename).name or not filename.endswith(".mp4"):
        raise HTTPException(status_code=404, detail="Preview not found")
    try:
        preview_root = (project_root(project_id) / "preview").resolve()
        target = (preview_root / filename).resolve()
        if target.parent != preview_root or not target.is_file():
            raise FileNotFoundError(filename)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Preview not found") from exc
    return FileResponse(target, media_type="video/mp4")


@app.put("/api/projects/{project_id}/lyrics")
def update_lyrics(project_id: str, request: LyricsUpdate) -> dict[str, int]:
    try:
        root = project_root(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc
    ordered = sorted(request.lyrics, key=lambda cue: cue.start)
    blocks = []
    word_cues = []
    for index, cue in enumerate(ordered, 1):
        if cue.end <= cue.start or not cue.text.strip():
            continue
        clean_text = repair_mojibake(cue.text.strip())
        blocks.append(f"{index}\n{_srt_time(cue.start)} --> {_srt_time(cue.end)}\n{clean_text}")
        display_words = clean_text.split()
        usable_words = cue.words if len(cue.words) == len(display_words) else []
        preserved = []
        previous_end = cue.start
        for display_word, word in zip(display_words, usable_words):
            start = max(previous_end, cue.start, min(cue.end, word.start))
            end = max(start + .01, min(cue.end, word.end))
            if start >= cue.end:
                break
            preserved.append({"text": display_word, "start": round(start, 4), "end": round(min(cue.end, end), 4)})
            previous_end = min(cue.end, end)
        word_cues.append({"start": round(cue.start, 4), "end": round(cue.end, 4), "text": clean_text, "words": preserved})
    (root / "input" / "lyrics.srt").write_text("\n\n".join(blocks) + "\n", encoding="utf-8")
    (root / "input" / "lyrics.words.json").write_text(
        json.dumps({"version": 2, "cues": word_cues}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {"saved": len(blocks)}


def _srt_time(value: float) -> str:
    milliseconds = max(0, round(value * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{seconds:02},{millis:03}"


@app.post("/api/projects/{project_id}/render", response_model=JobView, status_code=202)
def render(project_id: str, request: RenderRequest) -> dict:
    try:
        return render_queue.submit(project_id, request.options)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc


@app.get("/api/jobs", response_model=list[JobView])
def list_jobs() -> list[dict]:
    return repository.list()


@app.get("/api/jobs/{job_id}", response_model=JobView)
def get_job(job_id: str) -> dict:
    try:
        return repository.get(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc


@app.post("/api/jobs/{job_id}/cancel", response_model=JobView)
def cancel_job(job_id: str) -> dict:
    try:
        return render_queue.cancel(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc


@app.get("/api/jobs/{job_id}/files/{filename}")
def download(job_id: str, filename: str) -> FileResponse:
    try:
        job = repository.get(job_id)
        if filename != Path(filename).name or filename.startswith(".") or filename not in job["outputs"]:
            raise FileNotFoundError(filename)
        output_root = (project_root(job["project_id"]) / "output").resolve()
        target = (output_root / filename).resolve()
        if target.parent != output_root:
            raise FileNotFoundError(filename)
        if not target.exists():
            raise FileNotFoundError(filename)
    except (KeyError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail="File not found") from exc
    media_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    return FileResponse(target, media_type=media_type, filename=filename)
