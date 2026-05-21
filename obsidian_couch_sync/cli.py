from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from . import __version__
from .config import default_config_path, get_nested, load_config, save_config, set_nested
from .couch import CouchClient, CouchConfig
from .syncer import sync_once


def couch_from_config(cfg: dict[str, Any]) -> CouchClient:
    couch = cfg["couchdb"]
    return CouchClient(
        CouchConfig(
            url=couch["url"],
            database=couch["database"],
            username=couch.get("username", ""),
            password=couch.get("password", ""),
        )
    )


def cmd_config(args: argparse.Namespace) -> int:
    cfg_path = Path(args.config).expanduser() if args.config else default_config_path()
    cfg = load_config(cfg_path)
    if args.config_action == "path":
        print(cfg_path)
        return 0
    if args.config_action == "show":
        safe = json.loads(json.dumps(cfg))
        if safe.get("couchdb", {}).get("password"):
            safe["couchdb"]["password"] = "********"
        print(json.dumps(safe, ensure_ascii=False, indent=2))
        return 0
    if args.config_action == "get":
        print(get_nested(cfg, args.key))
        return 0
    if args.config_action == "set":
        set_nested(cfg, args.key, args.value)
        path = save_config(cfg, cfg_path)
        print(f"saved {args.key} to {path}")
        return 0
    raise SystemExit("unknown config action")


def cmd_ping(args: argparse.Namespace) -> int:
    cfg = load_config(Path(args.config).expanduser() if args.config else None)
    result = couch_from_config(cfg).ping()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def print_result(result: Any) -> None:
    print(
        "sync: "
        f"scanned={result.scanned} changed={result.changed} "
        f"written={result.written} skipped={result.skipped} errors={result.errors}"
    )


def cmd_sync(args: argparse.Namespace) -> int:
    cfg = load_config(Path(args.config).expanduser() if args.config else None)
    result = sync_once(cfg, couch_from_config(cfg), dry_run=args.dry_run, force=args.force)
    print_result(result)
    return 0


def cmd_watch(args: argparse.Namespace) -> int:
    cfg = load_config(Path(args.config).expanduser() if args.config else None)
    interval = args.interval
    print(f"watching every {interval}s; press Ctrl-C to stop", flush=True)
    while True:
        try:
            result = sync_once(cfg, couch_from_config(cfg), dry_run=False, force=False)
            print_result(result)
        except KeyboardInterrupt:
            return 0
        except Exception as exc:
            print(f"watch error: {exc}", file=sys.stderr)
        time.sleep(interval)


def unit_text(user: bool) -> str:
    executable = shutil_which("obsidian-couch-sync") or "/usr/bin/obsidian-couch-sync"
    return f"""[Unit]
Description=Obsidian Couch Sync
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart={executable} watch
Restart=always
RestartSec=10

[Install]
WantedBy={'default.target' if user else 'multi-user.target'}
"""


def shutil_which(name: str) -> str | None:
    for folder in os.environ.get("PATH", "").split(os.pathsep):
        candidate = Path(folder) / name
        if candidate.exists() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def cmd_service(args: argparse.Namespace) -> int:
    if args.service_action == "print":
        print(unit_text(args.user), end="")
        return 0
    unit = unit_text(args.user)
    if args.user:
        target = Path.home() / ".config" / "systemd" / "user" / "obsidian-couch-sync.service"
    else:
        target = Path("/etc/systemd/system/obsidian-couch-sync.service")
    if args.service_action == "install":
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(unit, encoding="utf-8")
        print(f"installed {target}")
        print("enable with:")
        print(
            "  systemctl --user enable --now obsidian-couch-sync.service"
            if args.user
            else "  sudo systemctl enable --now obsidian-couch-sync.service"
        )
        return 0
    raise SystemExit("unknown service action")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="obsidian-couch-sync",
        description="Sync local Markdown files into CouchDB for Obsidian LiveSync-style vaults.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--config", help="Path to config JSON")
    sub = parser.add_subparsers(dest="command", required=True)

    config = sub.add_parser("config", help="Manage configuration")
    config_sub = config.add_subparsers(dest="config_action", required=True)
    config_sub.add_parser("path", help="Print config path")
    config_sub.add_parser("show", help="Show effective config")
    get_p = config_sub.add_parser("get", help="Get a config value")
    get_p.add_argument("key")
    set_p = config_sub.add_parser("set", help="Set a config value")
    set_p.add_argument("key")
    set_p.add_argument("value")
    config.set_defaults(func=cmd_config)

    ping = sub.add_parser("ping", help="Check CouchDB connectivity")
    ping.set_defaults(func=cmd_ping)

    sync = sub.add_parser("sync", help="Run one sync")
    sync.add_argument("--dry-run", action="store_true", help="Scan and report without writing")
    sync.add_argument("--force", action="store_true", help="Write all files even if unchanged")
    sync.set_defaults(func=cmd_sync)

    watch = sub.add_parser("watch", help="Continuously sync on an interval")
    watch.add_argument("--interval", type=int, default=30)
    watch.set_defaults(func=cmd_watch)

    service = sub.add_parser("service", help="Generate or install a systemd service")
    service.add_argument("--user", action="store_true", help="Use user service instead of system service")
    service_sub = service.add_subparsers(dest="service_action", required=True)
    service_print = service_sub.add_parser("print", help="Print unit file")
    service_print.add_argument("--user", action="store_true", help="Use user service instead of system service")
    service_install = service_sub.add_parser("install", help="Install unit file")
    service_install.add_argument("--user", action="store_true", help="Use user service instead of system service")
    service.set_defaults(func=cmd_service)

    return parser


def normalize_argv(argv: list[str]) -> list[str]:
    """Let --config appear before or after the subcommand."""
    if "--config" not in argv:
        return argv
    out = list(argv)
    idx = out.index("--config")
    if idx + 1 >= len(out):
        return out
    pair = [out[idx], out[idx + 1]]
    del out[idx : idx + 2]
    return pair + out


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    argv = normalize_argv(argv)
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
