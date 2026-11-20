#!/usr/bin/env bash
# Usage: ./run_tlc.sh <cfg-basename> [extra TLC args]. Writes results/<cfg>.out.
# Runs on a lab host (rule 21), never the launching Mac. Uses `java` when it is
# on PATH, otherwise the eclipse-temurin:17-jre-alpine container.
# Env: WORKERS (default 4), HEAP (default 6g), TMO seconds (default 3600).
set -uo pipefail
cd "$(dirname "$0")"
name="$1"; shift
mkdir -p results states
if command -v java >/dev/null; then
  RUN=(java)
else
  RUN=(docker run --rm --user "$(id -u):$(id -g)" -v "$PWD:/work" -w /work eclipse-temurin:17-jre-alpine java)
fi
timeout "${TMO:-3600}" "${RUN[@]}" -XX:+UseParallelGC -Xmx"${HEAP:-6g}" -cp tla2tools.jar tlc2.TLC \
  -config "cfg/$name.cfg" -workers "${WORKERS:-4}" -metadir "states/$name" -deadlock "$@" \
  LandingController.tla > "results/$name.out" 2>&1
echo "rc=$?" >> "results/$name.out"
rm -rf "states/$name"
grep -E 'violated|Error:|No error|distinct states found|rc=|depth of the complete' "results/$name.out" | tail -5
