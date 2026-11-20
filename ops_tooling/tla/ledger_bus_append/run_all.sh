#!/usr/bin/env bash
# Runs every config (a finished run with nothing left to do is not a deadlock: -deadlock) on a lab host (rule 21). Needs java and tla2tools.jar beside this file
# (download: https://github.com/tlaplus/tlaplus/releases/download/v1.8.0/tla2tools.jar).
set -uo pipefail
cd "$(dirname "$0")"
mkdir -p results
for cfg in cfg/*.cfg; do
  name="$(basename "$cfg" .cfg)"
  timeout 1800 java -XX:+UseParallelGC -cp tla2tools.jar tlc2.TLC -config "$cfg" -workers "${TLC_WORKERS:-4}" -deadlock \
    -metadir "states/$name" LedgerBusAppend.tla > "results/$name.out" 2>&1
  echo "rc=$?" >> "results/$name.out"
  rm -rf "states/$name"
  echo "== $name"; grep -E 'violated|Error:|No error|distinct states found|rc=' "results/$name.out" | tail -4
done
