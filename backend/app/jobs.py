from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

from .config import settings
from .database import repository
from .media import analyze_audio, load_lyrics
from .projects import find_input, project_root
from .renderer import PulseRenderer, RenderSpec, nvenc_available
from .publication import create_release_pack
from .quality import run_quality_control
from .schemas import OutputKind, RenderOptions


DEFAULT_DURATIONS = {
    OutputKind.teaser: 15.0,
    OutputKind.chorus: 30.0,
    OutputKind.lyrics: 45.0,
}


class RenderQueue:
    def __init__(self) -> None:
        self.executor = ThreadPoolExecutor(
            max_workers=settings.render_concurrency,
            thread_name_prefix="pulse-render",
        )
        self._cancelled: set[str] = set()
        self._lock = threading.Lock()

    def submit(self, project_id: str, options: RenderOptions) -> dict:
        root = project_root(project_id)
        name = (root / "project.name").read_text(encoding="utf-8")
        job_id = uuid4().hex
        job = repository.create(job_id, project_id, name, options.model_dump(mode="json"))
        repository.update_project(project_id, settings=options.model_dump(mode="json"), status="queued")
        self.executor.submit(self._run, job_id, project_id, options)
        return job

    def cancel(self, job_id: str) -> dict:
        with self._lock:
            self._cancelled.add(job_id)
        return repository.update(job_id, status="cancelled", stage="Cancelled", message="Cancelled by user")

    def _is_cancelled(self, job_id: str) -> bool:
        with self._lock:
            return job_id in self._cancelled

    def _run(self, job_id: str, project_id: str, options: RenderOptions) -> None:
        try:
            root = project_root(project_id)
            audio = find_input(root, "song")
            cover = find_input(root, "cover")
            lyrics_path = find_input(root, "lyrics")
            if audio is None or cover is None:
                raise ValueError("Song or cover is missing.")

            repository.update(job_id, status="analyzing", progress=5, stage="Analyzing audio")
            profile = analyze_audio(audio)
            lyrics = load_lyrics(lyrics_path, profile.duration) if options.lyrics_enabled else []
            backgrounds = sorted((root / "input").glob("background_*.*"))
            renderer = PulseRenderer(audio, cover, lyrics, profile, options.editor, backgrounds)
            range_map = {item.output: item for item in options.ranges}
            completed: list[str] = []
            use_nvenc = options.encoder == "nvenc" or (options.encoder == "auto" and nvenc_available())
            encoder_label = "NVENC (GPU)" if use_nvenc else "libx264 (CPU)"
            span = 80 / len(options.outputs)

            for index, output in enumerate(options.outputs):
                if self._is_cancelled(job_id):
                    return
                custom = range_map.get(output)
                start = custom.start if custom else 0.0
                duration = (
                    custom.duration
                    if custom and custom.duration is not None
                    else profile.duration - start
                    if output == OutputKind.youtube
                    else DEFAULT_DURATIONS[output]
                )
                duration = min(duration, profile.duration - start)
                width, height = (1920, 1080) if output == OutputKind.youtube else (1080, 1920)
                filename = f"{output.value}.mp4"
                base_progress = 15 + index * span
                repository.update(
                    job_id,
                    status="rendering",
                    progress=round(base_progress),
                    stage=f"Rendering {output.value} · {encoder_label}",
                    outputs=completed,
                )
                last_reported = {"value": -1}

                def report(fraction: float, base: float = base_progress) -> None:
                    percent = min(94, round(base + fraction * span))
                    if percent != last_reported["value"]:
                        last_reported["value"] = percent
                        repository.update(job_id, progress=percent)

                renderer.render(
                    root / "output" / filename,
                    RenderSpec(start, duration, width, height, options.fps, options.quality, options.encoder, "youtube" if output == OutputKind.youtube else "tiktok"),
                    on_progress=report,
                )
                completed.append(filename)

            repository.update(job_id, progress=95, stage="Running quality control", outputs=completed)
            video_paths = [root / "output" / filename for filename in completed]
            quality = run_quality_control(video_paths, audio, lyrics, options.editor)
            project_record = repository.get_project(project_id)
            extras = create_release_pack(
                root, project_record["name"], completed,
                options.model_dump(mode="json"), project_record.get("analysis", {}), quality,
            )
            completed.extend(extras)

            repository.update(
                job_id,
                status="completed",
                progress=100,
                stage="Ready",
                message=f"{len(video_paths)} video(s) rendered · {len(quality['warnings'])} QC warning(s)",
                outputs=completed,
            )
            repository.update_project(project_id, status="completed", settings=options.model_dump(mode="json"))
        except Exception as exc:
            if not self._is_cancelled(job_id):
                repository.update(job_id, status="failed", stage="Failed", message=str(exc))
                try:
                    repository.update_project(project_id, status="failed")
                except KeyError:
                    pass


render_queue = RenderQueue()
