# Architecture

Pulse Studio is a local-first, single-workstation application. The browser is responsible for interaction and responsive preview; the backend owns durable project state, audio analysis, AI alignment, rendering, quality control, and release packaging.

## Components

### Frontend

- React and TypeScript
- Vite development/build pipeline
- HTML audio/video elements for synchronized preview
- Web Audio API for real-time frequency visualization
- Local project editor state submitted as validated render settings

The browser preview is intentionally lightweight. Export behavior must remain semantically equivalent even when the implementation differs from the OpenCV/Pillow renderer.

### API and project store

- FastAPI HTTP API
- Pydantic request and project schemas
- SQLite job/project index
- Filesystem project assets under `data/projects/<id>`
- Versioned `.pulseproject` import/export validation

The API is designed for a trusted local environment and currently has no authentication or multi-user isolation.

### Audio intelligence

- librosa for BPM, beats, downbeats, energy, onsets, and section boundaries
- Demucs `htdemucs` for vocal separation
- faster-whisper for local multilingual word timestamps
- monotonic line alignment that preserves supplied TXT wording
- vocal-activity recovery and a persistent alignment diagnostic report

### Renderer

- MoviePy for clip/audio orchestration
- OpenCV and Pillow for frame composition
- FFmpeg for encoding and muxing
- NVIDIA NVENC when available, with libx264 fallback

Background, cover, visualizer, lyrics, and overlay are separate conceptual layers. Background video time is derived deterministically from the song position, section index, user offset, playback speed, and loop mode.

High-resolution background videos are preserved unchanged for export. On upload,
the backend creates a seekable H.264 proxy capped at 960 pixels and 24 fps for
the browser editor. Preview proxies are disposable project cache files and are
never included in `.pulseproject` archives or final release packages.

### Render queue

The queue defaults to one active render. Jobs persist in SQLite and are recovered after interrupted application restarts. Increasing concurrency can increase throughput but also VRAM use and render variability.

## Persistent directories

```text
data/
  pulse-studio.db
  fonts/
  projects/<project-id>/
models/
  faster-whisper cache
  Torch/Demucs cache
```

Neither directory belongs in source control.

## Compatibility contracts

The public interchange contracts are:

- `schemas/preset-v1.schema.json`
- `schemas/project-v1.schema.json`
- `docs/CREATING_PRESETS.md`
- `docs/PULSEPROJECT.md`

Any incompatible change requires a format-version increment and migration strategy.

## Design principles

1. Automate the song-release workflow rather than becoming a general video editor.
2. Keep user media local by default.
3. Preserve supplied lyrics as authoritative text.
4. Keep preview and export behavior aligned.
5. Prefer deterministic, versioned project and preset formats.
6. Fail visibly and provide diagnostics instead of silently producing invalid releases.
