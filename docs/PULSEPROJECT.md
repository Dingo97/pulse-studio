# `.pulseproject` format

A Pulse project is a ZIP archive with the `.pulseproject` suffix. It contains original project inputs and a versioned `pulseproject.json` manifest. Rendered videos, model caches, temporary audio, installed application fonts, and databases are intentionally excluded.

```text
Example.pulseproject
|-- pulseproject.json
`-- input/
    |-- song.wav
    |-- cover.png
    |-- language.txt
    |-- lyrics.txt
    |-- lyrics.srt
    |-- lyrics.words.json
    `-- background_000.mp4
```

The manifest records editor/render settings, cached musical analysis, Auto Director decisions, and the exact asset list. See [`schemas/project-v1.schema.json`](../schemas/project-v1.schema.json).

## Security rules

- Imports accept only format version 1.
- Paths outside the `input/` allow-list are rejected.
- Archives are limited to 50 entries and 2.5 GB uncompressed.
- Executable files, plugins, installed fonts, and model files are not accepted.
- Extraction never trusts arbitrary archive paths.
- Asset names must match the published JSON Schema and server-side allow-list.

Projects can be exported from the dashboard and imported on another Pulse Studio installation. A future format version must provide an explicit migration rather than silently changing v1 semantics.

## Compatibility

Consumers must reject unknown major format versions. New optional fields may be introduced within a compatible version, but existing meanings must not change. Any breaking asset-layout or settings change requires a new format version and migration path.
