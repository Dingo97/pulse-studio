# Known limitations — v0.1.0-alpha.1

This is the first public alpha. Please report reproducible problems through the
GitHub issue templates, without attaching copyrighted songs or private projec
files.

- TXT lyric timing is automatic, not guaranteed. Layered vocals, heavy effects,
  very fast delivery, ad-libs, repeated lines, or text that differs from the
  performance may require review in the timing editor.
- The first TXT alignment downloads large Demucs and faster-whisper models and
  can take considerably longer than later runs.
- The application is designed for one trusted user on a local workstation. I
  has no authentication or multi-user isolation and must not be exposed to the
  public internet.
- NVIDIA CUDA and NVENC are the primary supported acceleration path. CPU expor
  works but is substantially slower; other GPU vendors are not yet validated.
- Windows 11 with Docker Desktop and WSL 2 is the documented installation path.
  Native Linux and macOS onboarding are not yet supported.
- Preview rendering is optimized for responsiveness and may differ slightly
  from the final full-resolution export.
- Project and preset schemas are versioned, but may still evolve before v1.0.
- Model downloads, source media, generated outputs, and installed fonts can use
  significant disk space and are not included in the repository.
