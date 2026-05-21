from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


DEFAULT_CONFIG = {
    "couchdb": {
        "url": "http://127.0.0.1:5984",
        "username": "",
        "password": "",
        "database": "obsidian",
    },
    "sync": {
        "vault_path": "",
        "root": "",
        "include": ["**/*.md"],
        "exclude": [".obsidian/**", ".git/**"],
        "state_path": "",
        "chunk_size": 900_000,
    },
}

ENV_MAP = {
    "couchdb.url": "OCS_COUCHDB_URL",
    "couchdb.username": "OCS_COUCHDB_USERNAME",
    "couchdb.password": "OCS_COUCHDB_PASSWORD",
    "couchdb.database": "OCS_COUCHDB_DATABASE",
    "sync.vault_path": "OCS_VAULT_PATH",
    "sync.root": "OCS_ROOT",
    "sync.state_path": "OCS_STATE_PATH",
}


def default_config_path() -> Path:
    root = os.environ.get("XDG_CONFIG_HOME")
    if root:
        return Path(root).expanduser() / "obsidian-couch-sync" / "config.json"
    return Path.home() / ".config" / "obsidian-couch-sync" / "config.json"


def deep_copy(value: Any) -> Any:
    return json.loads(json.dumps(value))


def merge_dict(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    out = deep_copy(base)
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = merge_dict(out[key], value)
        else:
            out[key] = value
    return out


def get_nested(data: dict[str, Any], dotted: str) -> Any:
    cur: Any = data
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            raise KeyError(dotted)
        cur = cur[part]
    return cur


def set_nested(data: dict[str, Any], dotted: str, value: Any) -> None:
    parts = dotted.split(".")
    cur: dict[str, Any] = data
    for part in parts[:-1]:
        nxt = cur.setdefault(part, {})
        if not isinstance(nxt, dict):
            raise ValueError(f"{part} is not an object")
        cur = nxt
    cur[parts[-1]] = value


def load_config(path: Path | None = None) -> dict[str, Any]:
    path = path or default_config_path()
    loaded: dict[str, Any] = {}
    if path.exists():
        loaded = json.loads(path.read_text(encoding="utf-8"))
    cfg = merge_dict(DEFAULT_CONFIG, loaded)
    for dotted, env_name in ENV_MAP.items():
        if env_name in os.environ:
            set_nested(cfg, dotted, os.environ[env_name])
    return cfg


def save_config(cfg: dict[str, Any], path: Path | None = None) -> Path:
    path = path or default_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return path
