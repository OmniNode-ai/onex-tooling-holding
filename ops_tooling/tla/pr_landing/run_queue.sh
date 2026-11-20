#!/usr/bin/env bash
cd "$(dirname "$0")"
for c in "$@"; do echo "== $c $(date -u +%H:%M:%SZ)"; ./run_tlc.sh "$c"; done
