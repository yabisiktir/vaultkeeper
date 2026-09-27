#!/bin/sh
# Compile NitHarness, run it in the CrossOver bottle "NIT" against the sandbox, print the log.
# Usage: run_nit.sh [watchdog-seconds]   (queries: put C:\nitdiff\in.tsv first)
set -e
H="$(cd "$(dirname "$0")" && pwd)"
C="$HOME/Library/Application Support/CrossOver/Bottles/NIT/drive_c"
WINE=/Applications/CrossOver.app/Contents/SharedSupport/CrossOver/bin/wine
BUILD="${TMPDIR:-/tmp}/nitharness"; mkdir -p "$BUILD"
mcs -nologo -r:System.Windows.Forms.dll -r:System.Drawing.dll "$H/NitHarness.cs" -out:"$BUILD/NitHarness.exe"
mkdir -p "$C/nitdiff"; cp "$BUILD/NitHarness.exe" "$C/nitdiff/nit80/"
cp "$C/nitdiff/nit80/NWN Installer Tool.exe.config" "$C/nitdiff/nit80/NitHarness.exe.config"
printf 'cd /d C:\\nitdiff\\nit80\r\nset NITDIFF_WATCHDOG=%s\r\nC:\\nitdiff\\nit80\\NitHarness.exe\r\necho exit=%%ERRORLEVEL%% > C:\\nitdiff\\exit.txt\r\n' "${1:-120}" > "$C/nitdiff/run.bat"
cp "${NITDIFF_RULES:-$H/dialog_rules.tsv}" "$C/nitdiff/dialog_rules.tsv"
rm -f "$C/nitdiff/out.tsv" "$C/nitdiff/harness.log"
# NIT saves My.Settings; the harness's copy must not carry answers between runs.
rm -rf "$C/users/crossover/AppData/Local/NitHarness"
"$WINE" --bottle NIT --wait-children cmd /c 'C:\nitdiff\run.bat' >/dev/null 2>&1 || true
cat "$C/nitdiff/harness.log" 2>/dev/null; cat "$C/nitdiff/exit.txt" 2>/dev/null
