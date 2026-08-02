# Pulse Studio Community Edition v0.1.0-alpha.2

This corrective alpha supersedes `v0.1.0-alpha.1` and contains the same first
public Pulse Studio feature set with a clean-install publication fix.

## Fixes since Alpha 1

- Corrected a publication-module import that prevented the backend from
  starting in a newly built Linux environment.
- Made the GitHub backend test environment match the Docker image by installing
  MoviePy explicitly without downgrading Pillow.
- Updated GitHub Actions runtimes and grouped future dependency updates.

See the [README](../README.md) for installation and workflow documentation and
[KNOWN_LIMITATIONS.md](../KNOWN_LIMITATIONS.md) before installing.
