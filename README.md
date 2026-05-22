# obsidian-couch-sync

`obsidian-couch-sync` is a headless command-line tool for servers and agents
that generate Markdown and need to push those files into a CouchDB-backed
Obsidian Self-hosted LiveSync-style vault.

It is designed for workflows like:

```text
cron / agent / script -> local Markdown folder -> CouchDB -> Obsidian mobile
```

## Status

This is an early alpha. It currently writes unencrypted LiveSync-style
parent/leaf documents. If your Self-hosted LiveSync vault uses end-to-end
encryption, test against a separate database first.

## Features

- `setup`, `status`, `config`, `ping`, `sync`, `watch`, and `service` commands.
- JSON config file plus environment variable overrides.
- One-shot sync and continuous polling mode.
- State tracking to skip unchanged files.
- Dry-run mode before writing to CouchDB.
- systemd unit generation.
- Minimal Debian package builder for `apt install ./package.deb`.

## Install

From source:

```bash
python3 -m pip install .
```

From the generated Debian package:

```bash
./debian/build-deb.sh
sudo apt install ./dist/obsidian-couch-sync_0.1.4_all.deb
```

## Quick Start

```bash
ocs setup
ocs status
ocs sync --dry-run
ocs sync
```

Or configure manually:

```bash
ocs config set couchdb.url http://127.0.0.1:5984
ocs config set couchdb.username obsidian
ocs config set couchdb.password 'secret'
ocs config set couchdb.database obsidian
ocs config set sync.vault_path '/path/to/Obsidian Vault'
ocs config set sync.root 'Hermes Daily Tasks'

ocs ping
ocs status
ocs sync --dry-run
ocs sync
```

`sync.root` is optional. When set, local files are written below that folder in
the remote vault.

## Commands

```bash
obsidian-couch-sync --help
ocs --help

ocs config path
ocs config show
ocs config get couchdb.url
ocs config set couchdb.url http://127.0.0.1:5984

ocs setup
ocs status
ocs ping
ocs sync --dry-run
ocs sync --force
ocs watch --interval 30
```

## Configuration

Default config path:

```text
~/.config/obsidian-couch-sync/config.json
```

Example:

```json
{
  "couchdb": {
    "url": "http://127.0.0.1:5984",
    "username": "obsidian",
    "password": "change-me",
    "database": "obsidian"
  },
  "sync": {
    "vault_path": "/srv/obsidian-vault",
    "root": "Hermes Daily Tasks",
    "include": ["**/*.md"],
    "exclude": [".obsidian/**", ".git/**"],
    "state_path": "",
    "chunk_size": 900000
  }
}
```

Environment overrides:

- `OCS_COUCHDB_URL`
- `OCS_COUCHDB_USERNAME`
- `OCS_COUCHDB_PASSWORD`
- `OCS_COUCHDB_DATABASE`
- `OCS_VAULT_PATH`
- `OCS_ROOT`
- `OCS_STATE_PATH`

## Running as a Service

Print a unit:

```bash
ocs service print --user
```

Install a user service:

```bash
ocs service install --user
systemctl --user enable --now obsidian-couch-sync.service
```

Install a system service:

```bash
sudo ocs service install
sudo systemctl enable --now obsidian-couch-sync.service
```

## Safety Notes

This tool writes directly to CouchDB. Always test against a non-production
database first.

Encrypted Self-hosted LiveSync vaults need the compatible encryption layer to
produce documents that the Obsidian plugin can decrypt. That is not implemented
in `0.1.0`.
