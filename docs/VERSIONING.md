# Versioning

## Scheme
Use Semantic Versioning: `MAJOR.MINOR.PATCH`.

A release tag is `vX.Y.Z`.

## Single source of truth
Keep the application version in one source-controlled location and expose it to the UI/build. Do not maintain separate hard-coded asset/release versions.

## Docker tags
Release `v1.4.2` publishes:
- `1.4.2`
- `1.4`
- `1`
- `latest`

## UI diagnostics
`Settings > About` shows installed version and build/commit identifier. When update checking is enabled, show the latest available release and release notes/link. The application does not self-update; deployment remains Docker/GitOps controlled.

## Release pipeline
A version tag triggers:
1. tests/lint/security checks
2. Docker build
3. GHCR push with version aliases
4. GitHub Release with generated release notes

Version bumps are intentional, reviewable changes. Releases are not inferred from arbitrary runtime state.
