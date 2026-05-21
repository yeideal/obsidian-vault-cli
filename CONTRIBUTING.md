# Contributing

Thanks for helping improve `obsidian-couch-sync`.

## Development

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
pytest
```

## Before submitting changes

```bash
python -m py_compile obsidian_couch_sync/*.py
pytest
./debian/build-deb.sh
```

## Safety

Do not commit real CouchDB credentials, Obsidian vault contents, generated
database dumps, or local `.deb` artifacts.
