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
# The bottle's Documents is the real ~/Documents: forbid writes to the real NWN
# folder and Vaultkeeper store, and fail if either changes anyway.
NWN="$HOME/Documents/Neverwinter Nights"; STORE="$HOME/Library/Application Support/Vaultkeeper"
snap() { find "$NWN" "$STORE" -type f 2>/dev/null | sort | while read -r f; do stat -f '%z %m %N' "$f"; done; }
before=$(mktemp); after=$(mktemp); snap > "$before"
NITDIFF_RULES="$HERE/dialog_rules.tsv" sandbox-exec -f "$HERE/no_real_nwn.sb" -D NWN="$NWN" -D STORE="$STORE" \
    "$H/run_nit.sh" 900 > "$OUT/run.txt" 2>&1 || true
snap > "$after"
if ! cmp -s "$before" "$after"; then echo "!! REAL FOLDERS CHANGED:"; diff "$before" "$after"; exit 1; fi
echo "real folders unchanged"; rm -f "$before" "$after"
# results.tsv keeps one line per form across runs (a re-run replaces its lines).
touch "$OUT/results.tsv"
if [ -s "$N/out.tsv" ]; then
    cut -f2 "$N/out.tsv" > "$OUT/.rerun"
    grep -v -F -w -f "$OUT/.rerun" "$OUT/results.tsv" > "$OUT/.kept" || true
    sort "$OUT/.kept" "$N/out.tsv" > "$OUT/results.tsv"; rm -f "$OUT/.rerun" "$OUT/.kept"
fi
cp "$N/shots/"* "$OUT/" 2>/dev/null || echo "no shots"
cat "$N/out.tsv" 2>/dev/null
rm -rf "$N/sb" "$N/in.tsv" "$N/out.tsv" "$N/shots"
