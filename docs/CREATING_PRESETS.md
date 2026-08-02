# Creating community presets

Pulse Studio presets are portable, declarative JSON documents. They describe an editor configuration and never contain executable code.

## The easy way

1. Open a project in the Live Editor.
2. Adjust visuals and typography until the preview looks right.
3. Select **Save current preset** to keep it in this browser.
4. Select **Export current preset** to download a `.pulsepreset.json` file.
5. Share that file directly or commit it to a public repository.

Use **Import preset** to install a file. Imported presets are validated, applied immediately and stored in browser `localStorage`; song audio, cover art and lyrics are never embedded.

## Creating one by hand

Copy [`presets/classic-pulse.pulsepreset.json`](../presets/classic-pulse.pulsepreset.json), change the metadata and settings, and validate it against [`schemas/preset-v1.schema.json`](../schemas/preset-v1.schema.json).

Required metadata:

- `$schema`: must identify the v1 Pulse schema.
- `formatVersion`: currently `1`.
- `name`: a short unique display name.
- `createdWith`: the Pulse Studio version used for testing.
- `settings`: one complete editor configuration.

Recommended metadata:

- `description`: what the preset is designed for.
- `author`: name or GitHub handle.
- `license`: use `CC0-1.0` when you want unrestricted reuse, or another explicit content license.
- `tags`: searchable terms such as `edm`, `minimal`, `word-by-word` or `noir`.

## Compatibility rules

- Unknown schema versions are rejected instead of being guessed.
- Unknown settings are rejected by the published JSON Schema.
- Presets may reference only built-in capabilities. They cannot load remote scripts.
- Media files and commercial fonts are not bundled in a v1 preset.
- A preset should be tested in both 16:9 and 9:16 output layouts.
- Keep text inside title-safe margins and test a long lyric line.

## Contributing to the official gallery

Place the preset under `presets/`, use the `.pulsepreset.json` suffix, and open a pull request containing:

- the preset file;
- a screenshot or short preview;
- author and license metadata;
- confirmation that it was tested in the live preview and final renderer.

The official collection accepts visual configurations only. Python, JavaScript, binaries and network dependencies do not belong in preset submissions.
