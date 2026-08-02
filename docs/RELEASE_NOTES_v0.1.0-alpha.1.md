# Pulse Studio Community Edition v0.1.0-alpha.1

The first public alpha of Pulse Studio turns a finished song, cover artwork,
and optional TXT/SRT lyrics into a coordinated lyric-video release package on
your own Windows workstation.

## Highlights

- Local-first React and FastAPI workflow with Docker Desktop onboarding.
- Demucs and faster-whisper lyric alignment with editable line and word timing.
- Beat-aware 16:9 and 9:16 editor with safe areas, smart crop, visualizers,
  overlays, custom fonts, community presets, and drag-and-drop positioning.
- NVIDIA CUDA/NVENC acceleration with a CPU fallback.
- Teaser, chorus, lyric cut, YouTube video, thumbnail, SRT, captions, metadata,
  quality report, and release ZIP exported together.
- Persistent projects and portable versioned `.pulseproject` archives.

## Install

1. Install Docker Desktop with its WSL 2 backend and a recent NVIDIA driver.
2. Clone or download the repository.
3. Run `onboarding.ps1 -Start` from PowerShell, or double-click
   `Start Pulse Studio.bat`.
4. Open <http://localhost:8080>.

The first TXT alignment downloads the required AI models. No paid API is used.

## Verification

- Backend test suite: 33 passed.
- Frontend production build: passed.
- npm high-severity audit: 0 vulnerabilities.
- Docker Compose configuration and NVIDIA/NVENC health check: passed.

This is an alpha release. Review [KNOWN_LIMITATIONS.md](../KNOWN_LIMITATIONS.md)
before installing and report reproducible defects using the issue templates.
