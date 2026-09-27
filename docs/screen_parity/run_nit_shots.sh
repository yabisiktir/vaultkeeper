#!/bin/sh
# Render NIT's own forms (headless, CrossOver bottle "NIT") for screen parity.
# Usage: run_nit_shots.sh [Form ...]   (default: every *.Designer.vb form)
# Output: docs/screen_parity/nit/<Form>.png + <Form>.controls.txt
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"; H="$HERE/../logic_audit/harness"
C="$HOME/Library/Application Support/CrossOver/Bottles/NIT/drive_c"; N="$C/nitdiff"
SRC="$HERE/../../../NWN Installer Tool v8.0/NWN Installer Tool"
OUT="$HERE/nit"; mkdir -p "$OUT"
"$H/make_sandbox.sh" "$C" >/dev/null
rm -rf "$N/shots"
if [ $# -gt 0 ]; then FORMS="$*"; else FORMS=$(cd "$SRC" && ls *.Designer.vb | sed 's/.Designer.vb//'); fi
: > "$N/in.tsv"
for f in $FORMS; do printf 'screenshot\t%s\n' "$f" >> "$N/in.tsv"; done
NITDIFF_RULES="$HERE/dialog_rules.tsv" "$H/run_nit.sh" 900 > "$OUT/run.txt" 2>&1 || true
cp "$N/out.tsv" "$OUT/out.tsv" 2>/dev/null || true
cp "$N/shots/"* "$OUT/" 2>/dev/null || echo "no shots"
rm -rf "$N/sb" "$N/in.tsv" "$N/out.tsv" "$N/shots"
cat "$OUT/out.tsv" 2>/dev/null
