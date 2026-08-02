# Security Policy

## Supported versions

Security fixes are currently applied to the latest development version only. Pulse Studio is pre-1.0 software intended for local use on a trusted workstation.

## Reporting a vulnerability

Do not open a public issue for a vulnerability that could expose local files, execute code, bypass archive validation, or permit unauthorized network access.

Until a dedicated security email is published, use GitHub's private vulnerability reporting feature on the repository's **Security** tab. Include reproduction steps, impact, affected versions, and any suggested mitigation.

## Deployment warning

Pulse Studio currently has no authentication or multi-user isolation. The official Docker Compose file binds both ports to `127.0.0.1`. Do not change that binding to expose the API or web UI to a LAN or the public internet. Remote deployment requires an authenticated reverse proxy, TLS, request limits, and additional operating-system isolation.

Uploaded files and imported `.pulseproject` archives are treated as untrusted input and should remain subject to strict size, extension, path, and schema validation.
