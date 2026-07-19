# Security

## Trust boundary
Mounting `/var/run/docker.sock` gives this application effectively host-level Docker control. Treat authenticated access to the UI as privileged administrative access.

## Required safeguards
- Never add destructive Docker functions such as remove, prune or volume deletion.
- Do not commit real credentials, tokens, webhook secrets, NAS credentials or private deployment paths.
- Form login is the default authentication mode; Basic Auth remains optional for trusted internal deployments.
- Session cookies must be signed, HttpOnly and SameSite-protected; production HTTPS deployments should enable Secure cookies.
- State-changing form/API operations must be protected against cross-site request forgery.
- Validate redirect targets and all user-controlled URLs/settings.
- Webhook delivery must have bounded timeouts/retries and must not leak secrets into logs.
- Backup/import must validate format/version before replacing persisted configuration.

## Docker socket
Do not claim that authentication makes direct Docker socket access safe. Anyone who gains control of this app can perform the Docker actions exposed by it. Keep the exposed action set intentionally narrow.

## Dependencies and CI
Run dependency/security checks in CI and keep dependencies within compatible supported versions. Security-related failures block release.
