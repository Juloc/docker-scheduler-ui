# Skill: Release

1. Read `docs/VERSIONING.md`.
2. Confirm tests/lint/security checks are green.
3. Bump the single version source intentionally.
4. Tag `vX.Y.Z`.
5. Build/publish GHCR tags `X.Y.Z`, `X.Y`, `X`, `latest`.
6. Create GitHub Release with generated notes.
7. Verify the running UI reports the expected version/build metadata.
