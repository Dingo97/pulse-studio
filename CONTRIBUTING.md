# Contributing to Pulse Studio

Thank you for helping improve Pulse Studio. The project is intentionally focused on one workflow: turning a finished song into a release-ready lyric-video package with minimal manual work.

## Before opening an issue

- Search existing issues and discussions.
- Run `onboarding.ps1` and include relevant diagnostic output.
- Confirm the problem still occurs on the latest `main` branch.
- Remove private lyrics, songs, artwork, usernames, and filesystem paths from logs.

## Reporting bugs

Include:

- Pulse Studio version or commit
- Windows, Docker Desktop, NVIDIA driver, and GPU versions
- exact reproduction steps
- expected and actual behavior
- relevant browser console and backend logs
- whether the issue affects preview, export, or both
- a minimal, rights-cleared test asset when media is required

For lyric alignment problems, include the selected language and sanitized excerpts from `lyrics.alignment.json` when possible.

## Feature proposals

Pulse Studio is not intended to become a general-purpose nonlinear editor. A feature is a strong fit when it reduces repetitive work in the song-to-release workflow, improves alignment/render reliability, or expands safe community customization.

Open a GitHub Discussion before implementing a large feature or changing a public project/preset format.

## Development setup

The recommended development environment is Windows 11, Docker Desktop with WSL 2, and an NVIDIA GPU.

```powershell
cd pulse-studio
docker compose up -d --build
```

For host-based development, see the README.

## Pull requests

1. Create a focused branch from `main`.
2. Keep unrelated formatting or refactors out of the change.
3. Add or update tests for behavior changes.
4. Run backend tests and the frontend production build.
5. Update schemas and documentation when changing presets or projects.
6. Never commit model files, project data, media, installed fonts, generated output, or secrets.
7. Complete the pull-request template.

## Required checks

```powershell
$env:PYTHONPATH = "backend"
python -m pytest backend\tests

cd frontend
npm ci
npm run build
```

Changes to rendering, text fitting, safe areas, or typography should include an intentional golden-frame update and an explanation in the pull request.

## Code style

- Python: clear type hints, small pure helpers where practical, and explicit error messages.
- TypeScript: strict typing; avoid `any` unless isolated and justified.
- UI: preserve keyboard usability, responsive behavior, and preview/export parity.
- Files: UTF-8 and English for public code, docs, UI strings, issues, and pull requests.

## Licensing

Before a contribution can be accepted, you must read and accept the [Contributor License Agreement](CONTRIBUTOR-LICENSE-AGREEMENT.md). The agreement lets the project distribute contributions in the source-available Community Edition and in separately licensed commercial editions while contributors retain ownership of their work.

Do not submit code, media, fonts, presets, or model files that you do not have permission to redistribute.
