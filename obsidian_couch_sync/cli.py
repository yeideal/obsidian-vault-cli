from __future__ import annotations

import argparse
import getpass
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from . import __version__
from .config import default_config_path, get_nested, load_config, save_config, set_nested
from .couch import CouchClient, CouchConfig, CouchError
from .state import default_state_path, load_state
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
        try:
            value = json.loads(args.value)
        except json.JSONDecodeError:
            value = args.value
        set_nested(cfg, args.key, value)
        path = save_config(cfg, cfg_path)
        print(f"saved {args.key} to {path}")
        return 0
    raise SystemExit("unknown config action")


def cmd_ping(args: argparse.Namespace) -> int:
    cfg = load_config(Path(args.config).expanduser() if args.config else None)
    result = couch_from_config(cfg).ping()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def prompt_text(label: str, default: str = "", *, secret: bool = False) -> str:
    suffix = f" [{default}]" if default else ""
    prompt = f"{label}{suffix}: "
    if secret:
        value = getpass.getpass(prompt)
    else:
        value = input(prompt)
    return value.strip() or default


def prompt_yes_no(label: str, default: bool = True) -> bool:
    suffix = "Y/n" if default else "y/N"
    value = input(f"{label} [{suffix}]: ").strip().lower()
    if not value:
        return default
    return value in {"y", "yes"}


def cmd_setup(args: argparse.Namespace) -> int:
    cfg_path = Path(args.config).expanduser() if args.config else default_config_path()
    cfg = load_config(cfg_path)
    print("Obsidian Couch Sync setup")
    print(f"Config: {cfg_path}")
    print()

    couch = cfg["couchdb"]
    sync_cfg = cfg["sync"]
    couch["url"] = prompt_text("CouchDB URL", couch.get("url") or "http://127.0.0.1:5984")
    couch["username"] = prompt_text("CouchDB username", couch.get("username", ""))
    existing_password = couch.get("password", "")
    password_label = "CouchDB password"
    if existing_password:
        password_label += " (leave blank to keep existing)"
    new_password = prompt_text(password_label, "", secret=True)
    if new_password:
        couch["password"] = new_password
    couch["database"] = prompt_text("CouchDB database", couch.get("database") or "obsidian")

    default_vault = sync_cfg.get("vault_path") or str(Path.home() / "Documents" / "Obsidian Vault")
    sync_cfg["vault_path"] = prompt_text("Local vault path", default_vault)
    sync_cfg["root"] = prompt_text("Remote root folder (optional)", sync_cfg.get("root", ""))

    save_config(cfg, cfg_path)
    print(f"\nSaved config to {cfg_path}")

    if prompt_yes_no("Test CouchDB connection now?", True):
        try:
            result = couch_from_config(cfg).ping()
            db = result.get("database", {})
            print(f"ok: CouchDB database {db.get('db_name', couch['database'])!r} is reachable")
        except Exception as exc:
            print(f"warning: CouchDB check failed: {exc}")

    if prompt_yes_no("Run a dry-run sync now?", True):
        try:
            result = sync_once(cfg, couch_from_config(cfg), dry_run=True, force=False)
            print_result(result)
        except Exception as exc:
            print(f"warning: dry-run failed: {exc}")

    print("\nNext steps:")
    print("  ocs status")
    print("  ocs sync --dry-run")
    print("  ocs sync")
    print("  ocs service install --user")
    return 0


def count_markdown(vault: Path) -> int:
    if not vault.is_dir():
        return 0
    return sum(1 for path in vault.rglob("*.md") if path.is_file())


def count_files(vault: Path) -> int:
    if not vault.is_dir():
        return 0
    return sum(1 for path in vault.rglob("*") if path.is_file())


def systemctl_status(user: bool) -> tuple[str, str]:
    cmd = ["systemctl"]
    if user:
        cmd.append("--user")
    cmd += ["is-active", "obsidian-couch-sync.service"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
    except Exception as exc:
        return "unknown", str(exc)
    return proc.stdout.strip() or "unknown", proc.stderr.strip()


def cmd_status(args: argparse.Namespace) -> int:
    cfg_path = Path(args.config).expanduser() if args.config else default_config_path()
    cfg = load_config(cfg_path)
    sync_cfg = cfg.get("sync", {})
    vault_path = str(sync_cfg.get("vault_path") or "").strip()
    vault = Path(vault_path).expanduser() if vault_path else Path()
    state_path = Path(sync_cfg.get("state_path") or default_state_path()).expanduser()
    state = load_state(state_path)

    print("Obsidian Couch Sync status")
    print(f"Version: {__version__}")
    config_ok = cfg_path.exists()
    vault_ok = bool(vault_path) and vault.is_dir()
    couch_ok = False
    print(f"Config: {cfg_path} ({'exists' if config_ok else 'missing'})")
    print(f"Vault: {vault if vault_path else '(not configured)'} ({'ok' if vault_ok else 'missing'})")
    if vault_ok:
        print(f"Files: {count_files(vault)}")
        print(f"Markdown files: {count_markdown(vault)}")
    print(f"Remote root: {sync_cfg.get('root') or '(vault root)'}")
    print(f"State: {state_path} ({'exists' if state_path.exists() else 'missing'})")
    print(f"Tracked files: {len(state.get('files', {}))}")
    if state.get("last_run_at"):
        print(f"Last run: {time.strftime('%Y-%m-%d %H:%M:%S %Z', time.localtime(state['last_run_at']))}")

    try:
        db = couch_from_config(cfg).ping().get("database", {})
        couch_ok = True
        print(f"CouchDB: ok ({db.get('db_name', cfg['couchdb']['database'])})")
    except (CouchError, Exception) as exc:
        print(f"CouchDB: error ({exc})")

    system_state, system_err = systemctl_status(False)
    user_state, user_err = systemctl_status(True)
    print(f"System service: {system_state}")
    if system_err:
        print(f"System service note: {system_err}")
    print(f"User service: {user_state}")
    if user_err:
        print(f"User service note: {user_err}")
    service_ok = system_state == "active" or user_state == "active"
    if config_ok and vault_ok and couch_ok and service_ok:
        print("Overall: ok")
        return 0
    if config_ok and vault_ok and couch_ok:
        print("Overall: warning (sync works manually, but service is not active)")
        return 0
    print("Overall: error")
    return 1


def print_result(result: Any) -> None:
    print(
        "sync: "
        f"scanned={result.scanned} changed={result.changed} "
        f"written={result.written} deleted={result.deleted} "
        f"skipped={result.skipped} errors={result.errors}",
        flush=True,
    )


def cmd_sync(args: argparse.Namespace) -> int:
    cfg = load_config(Path(args.config).expanduser() if args.config else None)
    result = sync_once(cfg, couch_from_config(cfg), dry_run=args.dry_run, force=args.force)
    print_result(result)
    return 0


def cmd_watch(args: argparse.Namespace) -> int:
    cfg_path = Path(args.config).expanduser() if args.config else None
    interval = args.interval
    print(f"watching every {interval}s; press Ctrl-C to stop", flush=True)
    while True:
        try:
            cfg = load_config(cfg_path)
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
ExecStart={executable} watch --interval 5
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
        description="Sync local vault files into CouchDB for Obsidian LiveSync-style vaults.",
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

    setup = sub.add_parser("setup", help="Interactive first-run configuration")
    setup.set_defaults(func=cmd_setup)

    status = sub.add_parser("status", help="Show configuration and runtime status")
    status.set_defaults(func=cmd_status)

    sync = sub.add_parser("sync", help="Run one sync")
    sync.add_argument("--dry-run", action="store_true", help="Scan and report without writing")
    sync.add_argument("--force", action="store_true", help="Write all files even if unchanged")
    sync.set_defaults(func=cmd_sync)

    watch = sub.add_parser("watch", help="Continuously sync on an interval")
    watch.add_argument("--interval", type=int, default=5)
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
