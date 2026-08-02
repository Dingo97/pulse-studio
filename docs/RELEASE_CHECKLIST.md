# Public Release Checklist

## Repository identity

- [ ] Have the Community, commercial, output-rights, trademark, and contributor licensing documents reviewed by qualified counsel.
- [ ] Choose the final GitHub owner and repository name.
- [ ] Add the final clone URL and repository-specific support/security links where appropriate.
- [ ] Add the final repository description, topics, and social preview image.
- [ ] Enable GitHub Discussions and private vulnerability reporting.

## Privacy and source audit

- [ ] Confirm `data/`, `models/`, `node_modules/`, `dist/`, caches, and `.env` are ignored.
- [ ] Search for local usernames, absolute paths, tokens, passwords, emails, song titles, and lyrics.
- [ ] Confirm no copyrighted media, model weights, or custom fonts are committed.
- [ ] Review Git history before pushing; deleting a file from the working tree does not remove it from prior commits.
- [ ] Confirm every accepted external contribution has an explicit CLA acceptance record.

## Quality gate

- [ ] Test at least ten rights-cleared songs across supported languages and vocal styles.
- [ ] Verify TXT alignment, SRT input, repeated choruses, intros, ad-libs, and fast vocals.
- [ ] Compare preview and export for every visualizer, animation, aspect ratio, and loop mode.
- [ ] Run the Windows onboarding flow on a clean machine.
- [ ] Test NVIDIA/NVENC and CPU fallback paths.
- [ ] Run backend tests, frontend build, and container tests.

## Release

- [ ] Finalize `CHANGELOG.md` and remove `Unreleased` from the release date.
- [ ] Create and push the intended release tag.
- [ ] Publish release notes, screenshots, and a short rights-cleared demo video.
- [ ] Document known limitations.
- [ ] Verify clone → onboarding → first export from the public repository.
