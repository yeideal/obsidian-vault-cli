from __future__ import annotations

import fnmatch
import hashlib
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .couch import CouchClient
from .livesync import build_livesync_delete_doc, build_livesync_docs, metadata_id, normalize_vault_path
from .state import default_state_path, load_state, save_state


@dataclass
class SyncResult:
    scanned: int = 0
    changed: int = 0
    written: int = 0
    pulled: int = 0
    deleted: int = 0
    skipped: int = 0
    errors: int = 0


def digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def should_exclude(rel: str, patterns: Iterable[str]) -> bool:
    return any(fnmatch.fnmatch(rel, pattern) for pattern in patterns)


def should_include(rel: str, patterns: Iterable[str]) -> bool:
    return any(fnmatch.fnmatch(rel, pattern) for pattern in patterns)


def iter_files(vault: Path, includes: list[str], excludes: list[str]) -> Iterable[Path]:
    for include in includes or ["**/*"]:
        for path in vault.glob(include):
            if not path.is_file():
                continue
            rel = path.relative_to(vault).as_posix()
            if should_exclude(rel, excludes):
                continue
            yield path


def rel_from_remote_path(remote_path: str, root: str) -> str | None:
    path = normalize_vault_path(remote_path)
    if not root:
        return path
    if path == root:
        return None
    prefix = f"{root}/"
    if not path.startswith(prefix):
        return None
    rel = path[len(prefix) :]
    if rel == root or rel.startswith(prefix):
        return None
    return rel


def iter_remote_file_docs(client: CouchClient, root: str, includes: list[str], excludes: list[str]) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for row in client.all_docs(include_docs=True):
        doc = row.get("doc") or {}
        remote_path = str(doc.get("path") or "")
        if doc.get("type") != "plain" or not remote_path:
            continue
        if str(doc.get("_id") or "") != metadata_id(remote_path):
            continue
        rel = rel_from_remote_path(remote_path, root)
        if rel is None:
            continue
        if not should_include(rel, includes):
            continue
        if should_exclude(rel, excludes):
            continue
        result[normalize_vault_path(remote_path)] = doc
    return result


def read_remote_content(client: CouchClient, doc: dict) -> str | None:
    if doc.get("deleted") is True:
        return None
    chunks: list[str] = []
    for child_id in doc.get("children") or []:
        leaf = client.get_doc(str(child_id))
        if not leaf or leaf.get("e_"):
            return None
        data = leaf.get("data")
        if not isinstance(data, str):
            return None
        chunks.append(data)
    return "".join(chunks)


def write_local_file(path: Path, content: str, mtime_ms: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    if mtime_ms:
        mtime = mtime_ms / 1000
        try:
            import os

            os.utime(path, (mtime, mtime))
        except OSError:
            pass


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
    includes = list(sync_cfg.get("include") or ["**/*"])
    excludes = list(sync_cfg.get("exclude") or [])
    state_path = Path(sync_cfg.get("state_path") or default_state_path()).expanduser()
    state = load_state(state_path)
    files_state = state.setdefault("files", {})
    chunk_size = int(sync_cfg.get("chunk_size") or 900_000)
    result = SyncResult()

    seen: set[str] = set()
    remote_docs = iter_remote_file_docs(client, root, includes, excludes)
    for path in sorted(set(iter_files(vault, includes, excludes))):
        result.scanned += 1
        rel = path.relative_to(vault).as_posix()
        target_path = normalize_vault_path(f"{root}/{rel}" if root else rel)
        seen.add(target_path)
        data = path.read_bytes()
        content = data.decode("utf-8", errors="replace")
        digest = digest_bytes(data)
        remote_doc = remote_docs.get(target_path) or client.get_doc(metadata_id(target_path))
        if not force and files_state.get(target_path) == digest:
            if remote_doc and remote_doc.get("deleted") is True:
                result.skipped += 1
                continue
            remote_content = read_remote_content(client, remote_doc) if remote_doc else None
            if remote_content is not None:
                remote_digest = digest_bytes(remote_content.encode("utf-8"))
                if remote_digest != digest:
                    result.changed += 1
                    if not dry_run:
                        write_local_file(path, remote_content, remote_doc.get("mtime"))
                        files_state[target_path] = remote_digest
                        result.pulled += 1
                    continue
            if remote_doc is not None:
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

    for target_path, remote_doc in sorted(remote_docs.items()):
        if target_path in seen or target_path in files_state or remote_doc.get("deleted") is True:
            continue
        rel = rel_from_remote_path(target_path, root)
        if rel is None:
            continue
        remote_content = read_remote_content(client, remote_doc)
        if remote_content is None:
            continue
        result.changed += 1
        if dry_run:
            continue
        write_local_file(vault / rel, remote_content, remote_doc.get("mtime"))
        files_state[target_path] = digest_bytes(remote_content.encode("utf-8"))
        seen.add(target_path)
        result.pulled += 1

    deleted_paths = sorted(set(files_state) - seen)
    for target_path in deleted_paths:
        existing = client.get_doc(metadata_id(target_path))
        if existing and existing.get("deleted") is True:
            files_state.pop(target_path, None)
            result.skipped += 1
            continue
        result.changed += 1
        if dry_run:
            continue
        client.put_doc(metadata_id(target_path), build_livesync_delete_doc(target_path, existing))
        files_state.pop(target_path, None)
        result.deleted += 1

    state["last_run_at"] = int(time.time())
    state["last_seen"] = sorted(seen)
    if not dry_run:
        save_state(state, state_path)
    return result
