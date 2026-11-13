# CS220 Team 5 - PrimeTime PX averaged power from gate-level simulation activity.
# Flow from Section 6: netlist + SDC + matching .db + VCD from netlist simulation.
#
#   DESIGN=fp32 PERIOD=40 pt_shell -f power/ptpx.tcl   (from repo root)

set REPO   [file normalize [file join [file dirname [info script]] ..]]
set DESIGN [expr {[info exists env(DESIGN)] ? $env(DESIGN) : "fp32"}]
set PERIOD [expr {[info exists env(PERIOD)] ? $env(PERIOD) : 40}]
set SYN    "$REPO/synthesis/${DESIGN}_p${PERIOD}"
set OUT    "$SYN/ptpx"
file mkdir $OUT
if {$DESIGN eq "fp32"} { set TOP fpu; set TB test_fp32_baseline } \
else                   { set TOP fpu_bf16_wrapper; set TB test_bf16_streaming_golden }
set VCD "$REPO/sim/${DESIGN}_p${PERIOD}/netlist.vcd"

set LIB "/usr/local/synopsys/pdk/SAED32_EDK/lib/stdcell_rvt/db_nldm/saed32rvt_ss0p7v125c.db"
set power_enable_analysis true
set power_analysis_mode averaged
set link_library [list "*" $LIB]

read_verilog "$SYN/${TOP}_netlist.v"
current_design $TOP
link_design $TOP
read_sdc "$SYN/${TOP}.sdc"
read_vcd -strip_path "$TB/dut" $VCD

update_timing
update_power
report_power                                  > "$OUT/power.log"
report_power -hierarchy                       > "$OUT/power_hier.log"
report_switching_activity -list_not_annotated > "$OUT/switching_not_annotated.log"
report_timing                                 > "$OUT/timing_pt.log"
puts "PTPX COMPLETE -> $OUT"
exit
