#!/bin/sh
# Render Vaultkeeper's screens for parity (see vk_shots.py) inside a macOS sandbox
# that forbids any write to the real NWN user folder and the real store. The
# script isolates itself too; this is the second guard (incident 2026-09-28).
set -eu
cd "$(dirname "$0")/../.."
NWN="$HOME/Documents/Neverwinter Nights"
STORE="$HOME/Library/Application Support/Vaultkeeper"
snap() { find "$NWN" "$STORE" -type f 2>/dev/null | sort | while read -r f; do stat -f '%z %m %N' "$f"; done; }
before=$(mktemp); after=$(mktemp)
snap > "$before"
QT_QPA_PLATFORM=offscreen sandbox-exec -f docs/screen_parity/no_real_nwn.sb \
    -D NWN="$NWN" -D STORE="$STORE" "${PYTHON:-.venv/bin/python}" docs/screen_parity/vk_shots.py "$@"
snap > "$after"
if cmp -s "$before" "$after"; then echo "real folders unchanged"; else
    echo "!! REAL FOLDERS CHANGED:"; diff "$before" "$after"; exit 1; fi
rm -f "$before" "$after"
