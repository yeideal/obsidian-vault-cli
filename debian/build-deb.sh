#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="$(python3 - "$ROOT" <<'PY'
import pathlib, re, sys
text = (pathlib.Path(sys.argv[1]) / "obsidian_couch_sync" / "__init__.py").read_text()
print(re.search(r'__version__ = "([^"]+)"', text).group(1))
PY
)"
PKG="$ROOT/dist/pkg"
OUT="$ROOT/dist/obsidian-couch-sync_${VERSION}_all.deb"

rm -rf "$PKG"
mkdir -p "$PKG/DEBIAN" "$PKG/usr/lib/obsidian-couch-sync" "$PKG/usr/bin" "$PKG/lib/systemd/system"
cp "$ROOT/debian/control" "$PKG/DEBIAN/control"
cp "$ROOT/debian/postinst" "$PKG/DEBIAN/postinst"
cp "$ROOT/debian/prerm" "$PKG/DEBIAN/prerm"
chmod 0755 "$PKG/DEBIAN/postinst" "$PKG/DEBIAN/prerm"
cp -a "$ROOT/obsidian_couch_sync" "$PKG/usr/lib/obsidian-couch-sync/"
find "$PKG/usr/lib/obsidian-couch-sync" -type d -name '__pycache__' -prune -exec rm -rf {} +
cp "$ROOT/systemd/obsidian-couch-sync.service" "$PKG/lib/systemd/system/"
cat > "$PKG/usr/bin/obsidian-couch-sync" <<'SH'
#!/usr/bin/env bash
PYTHONPATH=/usr/lib/obsidian-couch-sync exec python3 -m obsidian_couch_sync.cli "$@"
SH
chmod 0755 "$PKG/usr/bin/obsidian-couch-sync"
ln -s obsidian-couch-sync "$PKG/usr/bin/ocs"

mkdir -p "$ROOT/dist"
dpkg-deb --build "$PKG" "$OUT"
echo "$OUT"
