from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def default_state_path() -> Path:
    root = os.environ.get("XDG_STATE_HOME")
    if root:
        return Path(root).expanduser() / "obsidian-couch-sync" / "state.json"
    return Path.home() / ".local" / "state" / "obsidian-couch-sync" / "state.json"


def load_state(path: Path | None = None) -> dict[str, Any]:
    path = path or default_state_path()
    if not path.exists():
        return {"files": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"files": {}}
    if not isinstance(data, dict):
        return {"files": {}}
    data.setdefault("files", {})
    return data


def save_state(state: dict[str, Any], path: Path | None = None) -> Path:
    path = path or default_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return path
