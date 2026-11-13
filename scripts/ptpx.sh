#!/usr/bin/env bash
# PrimeTime PX averaged power using the netlist-simulation VCD.
#   DESIGN=fp32 PERIOD=40 bash scripts/ptpx.sh
set -euo pipefail
source "$(dirname "$0")/common.sh"
[ -f "$SIM_DIR/netlist.vcd" ] || { echo "missing $SIM_DIR/netlist.vcd - run scripts/netlist_sim.sh first"; exit 1; }
DESIGN=$DESIGN PERIOD=$PERIOD pt_shell -f power/ptpx.tcl | tee "$SYN_DIR/ptpx_run.log" | tail -5
