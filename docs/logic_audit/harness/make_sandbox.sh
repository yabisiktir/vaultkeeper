#!/bin/sh
# Build a tiny NIT sandbox inside the CrossOver bottle. Usage: make_sandbox.sh <bottle drive_c>
# Everything lives under drive_c/nitdiff/sb; nothing points outside it.
set -e
C="$1"; SB="$C/nitdiff/sb"; W='C:\nitdiff\sb'
rm -rf "$SB"; mkdir -p "$SB/store" "$SB/temp" "$SB/downloads" "$SB/eelib/bin/win32" "$SB/eelib/data/nwm" "$SB/eelib/ovr"
: > "$SB/eelib/bin/win32/nwmain.exe"; : > "$SB/eelib/data/nwm/Chapter1.nwm"
U="$SB/user"; mkdir -p "$U"
# Alias set and order copied from a real EE nwn.ini (extra aliases make NIT throw).
printf '[Alias]\r\n' > "$U/nwn.ini"
for a in CRASHREPORT MODELCOMPILER CACHE NWSYNC OLDSERVERVAULT PATCH DEVELOPMENT HD0 MODULES SAVES OVERRIDE HAK SCREENSHOTS CURRENTGAME LOGS TEMP TEMPCLIENT LOCALVAULT DMVAULT SERVERVAULT DATABASE PORTRAITS AMBIENT MOVIES MUSIC TLK; do
  if [ "$a" = HD0 ]; then printf 'HD0=%s\\user\r\n' "$W" >> "$U/nwn.ini"; continue; fi
  d=$(echo "$a" | tr 'A-Z' 'a-z'); mkdir -p "$U/$d"; printf '%s=%s\\user\\%s\r\n' "$a" "$W" "$d" >> "$U/nwn.ini"
done
mkdir -p "$U/erf" "$U/nwm" "$U/texturepacks"
: > "$U/nwnplayer.ini"
echo "sandbox ready: $(du -sh "$SB" | cut -f1)"
