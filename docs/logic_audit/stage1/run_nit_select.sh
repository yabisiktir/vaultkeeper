#!/bin/sh
# NIT's Download Project selection for each URL in vault_select_urls.txt (1c follow-up).
# Usage: run_nit_select.sh <outdir>
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"; H="$HERE/../harness"
C="$HOME/Library/Application Support/CrossOver/Bottles/NIT/drive_c"; N="$C/nitdiff"
OUT="$1"; mkdir -p "$OUT"
"$H/make_sandbox.sh" "$C" >/dev/null
rm -f "$N/select.tsv"
while read -r url; do [ -n "$url" ] && printf 'vault-select\t%s\n' "$url"; done < "$HERE/vault_select_urls.txt" > "$N/in.tsv"
"$H/run_nit.sh" 1200 > "$OUT/run.txt" 2>&1 || true
cp "$N/harness.log" "$OUT/nit_harness.log" 2>/dev/null || true
cp "$N/out.tsv" "$OUT/nit_out.tsv" 2>/dev/null || true
cp "$N/select.tsv" "$OUT/nit_select.tsv" 2>/dev/null || echo "no select.tsv"
rm -rf "$N/sb" "$N/in.tsv" "$N/out.tsv" "$N/select.tsv"
