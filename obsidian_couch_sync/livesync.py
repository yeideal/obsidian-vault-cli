from __future__ import annotations

import hashlib
import time
from pathlib import PurePosixPath


def normalize_vault_path(path: str) -> str:
    path = path.replace("\\", "/").strip("/")
    parts = [part for part in PurePosixPath(path).parts if part not in ("", ".")]
    if any(part == ".." for part in parts):
        raise ValueError(f"invalid vault path: {path!r}")
    return "/".join(parts)


def leaf_id(parent_path: str, index: int, content: str) -> str:
    digest = hashlib.sha1(f"{parent_path}\0{index}\0{content}".encode("utf-8")).hexdigest()
    return f"h:+{digest[:24]}"


def build_livesync_docs(
    path: str,
    content: str,
    *,
    ctime_ms: int | None = None,
    mtime_ms: int | None = None,
    chunk_size: int = 900_000,
) -> list[dict]:
    """Build unencrypted LiveSync-style parent and leaf docs.

    Self-hosted LiveSync databases that use encryption require the plugin's
    encryption layer. This builder intentionally emits plain leaf documents.
    """
    now_ms = int(time.time() * 1000)
    path = normalize_vault_path(path)
    ctime_ms = ctime_ms or now_ms
    mtime_ms = mtime_ms or now_ms
    chunks = [content[i : i + chunk_size] for i in range(0, len(content), chunk_size)] or [""]
    child_ids = [leaf_id(path, idx, chunk) for idx, chunk in enumerate(chunks)]
    parent = {
        "_id": path,
        "path": path,
        "children": child_ids,
        "ctime": ctime_ms,
        "mtime": mtime_ms,
        "size": len(content.encode("utf-8")),
        "type": "plain",
        "eden": {},
        "deleted": False,
    }
    leaves = [
        {
            "_id": child_id,
            "data": chunk,
            "type": "leaf",
        }
        for child_id, chunk in zip(child_ids, chunks)
    ]
    return [parent, *leaves]
