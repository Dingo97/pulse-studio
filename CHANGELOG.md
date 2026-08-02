# Changelog

All notable changes to Pulse Studio will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project intends to follow [Semantic Versioning](https://semver.org/) after the public v1.0 release.

## [Unreleased]

## [0.1.0-alpha.2] - 2026-08-02

### Fixed

- Corrected the publication-module font import exposed by the clean Linux CI environment.
- Installed MoviePy explicitly in the backend CI job to match the Docker image.
- Updated GitHub Actions runtimes and grouped future Dependabot updates.

## [0.1.0-alpha.1] - 2026-08-02

First public Community Edition alpha.

### Fixed

- Preserved word-level timing through the editor and export pipeline.
- Prevented stale word highlighting during vocal pauses.
- Split merged Whisper tokens across the corresponding supplied lyric words.
- Repaired common UTF-8/Windows-1252 mojibake in imported and edited lyrics.
- Stabilized smart crop during continuous background playback.

### Changed

- Replaced the MIT license with the PolyForm Perimeter License 1.0.0 for the source-available Community Edition.
- Documented commercial licensing, user ownership of generated output, trademark rules, and the contributor licensing agreement.

### Added

- Lightweight GPU-assisted preview proxies for high-resolution background videos.
- Scratches, light leaks, film burn, rain, scanlines, bokeh, and prism overlays with matching live preview and export rendering.
- Local-first project dashboard and persistent render queue
- Demucs and faster-whisper TXT lyric alignment with word timing diagnostics
- Live 16:9/9:16 visual editor with drag-and-drop layout
- Beat-aware cover animation and real audio spectrum visualizers
- Synchronized image/video backgrounds and essential timing/filter controls
- Platform safe areas, intelligent text fitting, and word-by-word lyrics
- Persistent custom font library and community preset format
- Auto Director release-range suggestions
- NVENC/CPU export package with thumbnail, subtitles, metadata, captions, and QC
- Portable `.pulseproject` archives and Windows onboarding diagnostics
- Golden-frame and synchronization regression tests
