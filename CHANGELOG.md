# Changelog

## 0.1.4

- Write LiveSync metadata IDs in lower-case path form while preserving the original `path`.
- Use content-hash leaf IDs compatible with plain, unencrypted LiveSync documents.
- Repair missing remote metadata documents even when local state says the file content is unchanged.

## 0.1.3

- Make `watch` reload configuration every loop.
- Refuse to sync when `sync.vault_path` is empty instead of scanning cwd.

## 0.1.2

- Add an `Overall:` health line and meaningful status exit code.
- Avoid stopping the systemd service during Debian package upgrades.

## 0.1.1

- Add `ocs setup` for guided first-run configuration.
- Add `ocs status` for config, vault, CouchDB, state, and systemd checks.
- Restore GitHub Actions CI workflow.
- Ignore ambient proxy environment variables for CouchDB requests.

## 0.1.0

- Initial CLI with `config`, `ping`, `sync`, `watch`, and `service` commands.
- CouchDB writer with state tracking and dry-run support.
- LiveSync-style parent/leaf document generation for unencrypted databases.
- systemd service generation and minimal Debian package builder.
