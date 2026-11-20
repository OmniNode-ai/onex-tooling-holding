#!/usr/bin/env bash
# Usage: ./run_queue.sh [<cfg> ...]: runs each config in turn; with no argument, every cfg/*.cfg.
cd "$(dirname "$0")"
if [ "$#" -eq 0 ]; then set -- $(ls cfg | sed 's/\.cfg$//'); fi
for c in "$@"; do echo "== $c $(date -u +%H:%M:%SZ)"; ./run_tlc.sh "$c"; done
