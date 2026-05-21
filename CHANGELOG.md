# Changelog

## Unreleased

- Add `ocs setup` for guided first-run configuration.
- Add `ocs status` for config, vault, CouchDB, state, and systemd checks.
- Restore GitHub Actions CI workflow.

## 0.1.0

- Initial CLI with `config`, `ping`, `sync`, `watch`, and `service` commands.
- CouchDB writer with state tracking and dry-run support.
- LiveSync-style parent/leaf document generation for unencrypted databases.
- systemd service generation and minimal Debian package builder.
