#!/usr/bin/env bash
# Usage: ./run_tlc.sh <cfg-basename> [extra TLC args]. Writes results/<cfg>.out.
# Env: JAVA (default: java on PATH), WORKERS (default 4), HEAP (default 6g), TMO seconds (default 2400).
set -uo pipefail
cd "$(dirname "$0")"
JAVA="${JAVA:-java}"
name="$1"; shift
mkdir -p results states
timeout "${TMO:-2400}" "$JAVA" -XX:+UseParallelGC -Xmx${HEAP:-6g} -cp tla2tools.jar tlc2.TLC \
  -config "$name.cfg" -workers "${WORKERS:-4}" -metadir "states/$name" -deadlock "$@" PrLanding.tla \
  > "results/$name.out" 2>&1
echo "rc=$?" >> "results/$name.out"
rm -rf "states/$name"
grep -E 'violated|Error:|No error|states generated|distinct states found|rc=|Finished in|depth of the complete' "results/$name.out" | tail -6
