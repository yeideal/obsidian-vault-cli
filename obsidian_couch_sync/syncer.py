from __future__ import annotations

import fnmatch
import hashlib
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .couch import CouchClient
from .livesync import build_livesync_docs, metadata_id, normalize_vault_path
from .state import default_state_path, load_state, save_state


@dataclass
class SyncResult:
    scanned: int = 0
    changed: int = 0
    written: int = 0
    skipped: int = 0
    errors: int = 0


def digest_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def should_exclude(rel: str, patterns: Iterable[str]) -> bool:
    return any(fnmatch.fnmatch(rel, pattern) for pattern in patterns)


def iter_markdown(vault: Path, includes: list[str], excludes: list[str]) -> Iterable[Path]:
    for include in includes or ["**/*.md"]:
        for path in vault.glob(include):
            if not path.is_file():
                continue
            rel = path.relative_to(vault).as_posix()
            if should_exclude(rel, excludes):
                continue
            yield path


def sync_once(cfg: dict, client: CouchClient, *, dry_run: bool = False, force: bool = False) -> SyncResult:
    sync_cfg = cfg.get("sync", {})
    vault_path = str(sync_cfg.get("vault_path") or "").strip()
    if not vault_path:
        raise ValueError("sync.vault_path is not configured; run `ocs setup` first")
    vault = Path(vault_path).expanduser()
    if not vault.exists():
        raise FileNotFoundError(f"vault path does not exist: {vault}")
    if not vault.is_dir():
        raise NotADirectoryError(f"vault path is not a directory: {vault}")

    root = normalize_vault_path(str(sync_cfg.get("root") or ""))
    includes = list(sync_cfg.get("include") or ["**/*.md"])
    excludes = list(sync_cfg.get("exclude") or [])
    state_path = Path(sync_cfg.get("state_path") or default_state_path()).expanduser()
    state = load_state(state_path)
    files_state = state.setdefault("files", {})
    chunk_size = int(sync_cfg.get("chunk_size") or 900_000)
    result = SyncResult()

    seen: set[str] = set()
    for path in sorted(set(iter_markdown(vault, includes, excludes))):
        result.scanned += 1
        rel = path.relative_to(vault).as_posix()
        target_path = normalize_vault_path(f"{root}/{rel}" if root else rel)
        seen.add(target_path)
        content = path.read_text(encoding="utf-8", errors="replace")
        digest = digest_text(content)
        if not force and files_state.get(target_path) == digest:
            if client.get_doc(metadata_id(target_path)) is not None:
                result.skipped += 1
                continue
        result.changed += 1
        if dry_run:
            continue
        stat = path.stat()
        docs = build_livesync_docs(
            target_path,
            content,
            ctime_ms=int(stat.st_ctime * 1000),
            mtime_ms=int(stat.st_mtime * 1000),
            chunk_size=chunk_size,
        )
        client.bulk_docs(docs)
        files_state[target_path] = digest
        result.written += 1

    state["last_run_at"] = int(time.time())
    state["last_seen"] = sorted(seen)
    if not dry_run:
        save_state(state, state_path)
    return result
