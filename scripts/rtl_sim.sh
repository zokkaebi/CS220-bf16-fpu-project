#!/usr/bin/env bash
# RTL simulation of the FP32 baseline with VCS (or Icarus if VCS is absent).
#   bash scripts/rtl_sim.sh            # 12 corner + 16 random-constrained cases
#   bash scripts/rtl_sim.sh regression # + 4,000-case random / full-range regression
set -euo pipefail
DESIGN=fp32 source "$(dirname "$0")/common.sh"
mkdir -p sim/rtl
python3 test_vectors/fp32_golden_model.py --out test_vectors/fp32_baseline_vectors.hex
python3 test_vectors/fp32_golden_model.py --out test_vectors/fp32_regression.hex \
  --random 2000 --full-range 2000 --no-corner --seed 7
VECS="test_vectors/fp32_baseline_vectors.hex"
[ "${1:-}" = regression ] && VECS="$VECS test_vectors/fp32_regression.hex"
if command -v vcs >/dev/null; then
  vcs -full64 -sverilog +v2k -timescale=1ns/100ps -top $TB $RTL $TB_FILE -o sim/rtl/simv -l sim/rtl/compile.log >/dev/null
  RUN="sim/rtl/simv"
else
  iverilog -g2012 -s $TB -o sim/rtl/sim.vvp $RTL $TB_FILE
  RUN="vvp sim/rtl/sim.vvp"
fi
for v in $VECS; do
  echo "== $v"
  $RUN +VECTORS=$v | tee "sim/rtl/$(basename "$v" .hex).log" | grep -E "RESULT|FAIL|PASSED"
done
