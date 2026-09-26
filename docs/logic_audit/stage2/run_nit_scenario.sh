#!/bin/sh
# Run a stage-2 scenario in NIT (headless, sandboxed). Usage: run_nit_scenario.sh <scenario.tsv> <outdir>
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"; H="$HERE/../harness"
C="$HOME/Library/Application Support/CrossOver/Bottles/NIT/drive_c"; N="$C/nitdiff"
OUT="$2"; mkdir -p "$OUT"
rm -f "$OUT/attempts.txt"
# NIT's LazWorks FileOperations has a queue race (items added after the worker
# drained the queue are never processed -> "Delete/Copy failure" with no message).
# Retry until a run is clean, so comparisons use a deterministic NIT outcome.
for attempt in 1 2 3 4 5; do
  "$H/make_sandbox.sh" "$C" >/dev/null
  rm -rf "$N/fixtures" "$N/fx"; python3 "$HERE/make_fixtures.py" "$N/fx"
  mv "$N/fx/fixtures" "$N/fixtures"; cp -R "$N/fx/preexisting/." "$N/sb/user/"; rm -rf "$N/fx"
  cp "$1" "$N/scenario.tsv"
  printf 'scenario\tC:\\nitdiff\\scenario.tsv\n' > "$N/in.tsv"
  "$H/run_nit.sh" 600 > "$OUT/run.txt" 2>&1 || true
  if grep -q "Compilation failed" "$OUT/run.txt"; then cat "$OUT/run.txt"; exit 1; fi
  cp "$N/harness.log" "$OUT/nit_harness.log"; cp "$N/out.tsv" "$OUT/nit_out.tsv" 2>/dev/null || true; cp "$N/snaps.tsv" "$OUT/nit_snaps.tsv" 2>/dev/null || echo "no snapshots"
  cp "$N/sb/store/NIT Store/Backups/"*Log*.txt "$OUT/nit_app.log" 2>/dev/null || true
  rm -rf "$N/sb" "$N/fixtures" "$N/in.tsv" "$N/out.tsv" "$N/snaps.tsv"
  fails=$(grep -cE "^ +(Delete|Copy|Move) failure:" "$OUT/nit_app.log" 2>/dev/null || true)
  echo "attempt $attempt: $fails I/O failures" >> "$OUT/attempts.txt"
  [ "${fails:-0}" = "0" ] && break
done
grep -c . "$OUT/nit_snaps.tsv" 2>/dev/null || true
