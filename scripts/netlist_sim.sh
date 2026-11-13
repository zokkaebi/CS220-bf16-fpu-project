#!/usr/bin/env bash
# Gate-level simulation of the synthesized netlist with VCS, SDF back-annotated
# at the synthesis clock period, and a VCD dump for PrimeTime power.
#   DESIGN=fp32 PERIOD=40 bash scripts/netlist_sim.sh          # SDF-timed
#   DESIGN=fp32 PERIOD=40 MODE=zero bash scripts/netlist_sim.sh # zero-delay functional
set -euo pipefail
source "$(dirname "$0")/common.sh"
MODE="${MODE:-sdf}"
NET="$SYN_DIR/${TOP}_netlist.v"; SDF="$SYN_DIR/${TOP}.sdf"
[ -f "$NET" ] || { echo "missing $NET - run scripts/syn.sh first"; exit 1; }
if [ ! -f "$SAED32_V" ]; then
  echo "SAED32 cell models not found at $SAED32_V"
  echo "find them with:  find /usr/local/synopsys/pdk/SAED32_EDK/lib/stdcell_rvt -name '*.v'"
  echo "then rerun with: SAED32_V=<path> ..."; exit 1
fi
mkdir -p "$SIM_DIR"
OPTS="-full64 -sverilog +v2k -timescale=1ns/1ps -top $TB -pvalue+$TB.PERIOD=$PERIOD +neg_tchk -debug_access+r"
if [ "$MODE" = sdf ]; then
  OPTS="$OPTS -sdf max:$TB.dut:$SDF +sdfverbose"
else
  OPTS="$OPTS +notimingcheck +nospecify +delay_mode_zero"
fi
vcs $OPTS -v "$SAED32_V" "$NET" "$TB_FILE" -o "$SIM_DIR/simv" -l "$SIM_DIR/compile.log" >/dev/null
if [ "$DESIGN" = fp32 ]; then
  echo "== corner + random-constrained cases"
  "$SIM_DIR/simv" +VECTORS=test_vectors/fp32_baseline_vectors.hex | tee "$SIM_DIR/netlist_baseline.log" | grep -E "RESULT|FAIL|PASSED|Error|Timing violation" | head -20
  echo "== 4,000-case regression (VCD for PrimeTime)"
  "$SIM_DIR/simv" +VECTORS=test_vectors/fp32_regression.hex +VCD="$SIM_DIR/netlist.vcd" | tee "$SIM_DIR/netlist_regression.log" | grep -E "RESULT|FAIL|PASSED|Error|Timing violation" | head -20
else
  "$SIM_DIR/simv" +VCD="$SIM_DIR/netlist.vcd" | tee "$SIM_DIR/netlist_streaming.log" | grep -E "PASSED|MISMATCH|Error|Timing violation" | head -20
fi
ls -la "$SIM_DIR/netlist.vcd"
