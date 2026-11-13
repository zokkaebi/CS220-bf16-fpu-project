#!/usr/bin/env bash
# Synthesize one design at one or more clock periods (runs in parallel, survives logout).
#   DESIGN=fp32 bash scripts/syn.sh 40 36 32
#   DESIGN=bf16 bash scripts/syn.sh 10 9 8
set -euo pipefail
source "$(dirname "$0")/common.sh"
[ $# -ge 1 ] || { echo "usage: DESIGN=fp32|bf16 bash scripts/syn.sh PERIOD [PERIOD...]"; exit 1; }
mkdir -p synthesis/logs
for P in "$@"; do
  DESIGN=$DESIGN PERIOD=$P nohup dc_shell -f synthesis/compile_sweep.tcl \
    > "synthesis/logs/${DESIGN}_p${P}.log" 2>&1 &
  echo "started $DESIGN @ ${P} ns (pid $!), log: synthesis/logs/${DESIGN}_p${P}.log"
done
