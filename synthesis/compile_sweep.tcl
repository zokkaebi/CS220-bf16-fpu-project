# CS220 Team 5 - Design Compiler synthesis at a chosen clock period.
#
# Same library, corner and constraints as every earlier run (SAED32 RVT,
# SS 0.7 V 125 C, 0.1 ns I/O delay, 0.2 ns uncertainty); only the clock
# period changes, so results at different periods are directly comparable.
#
#   DESIGN=fp32 PERIOD=40 dc_shell -f synthesis/compile_sweep.tcl   (from repo root)
#   DESIGN=bf16 PERIOD=9  dc_shell -f synthesis/compile_sweep.tcl
#
# Outputs: synthesis/<design>_p<period>/ (reports, netlist, SDC, SDF)

set REPO   [file normalize [file join [file dirname [info script]] ..]]
set DESIGN [expr {[info exists env(DESIGN)] ? $env(DESIGN) : "fp32"}]
set PERIOD [expr {[info exists env(PERIOD)] ? $env(PERIOD) : 40}]
set OUT    "$REPO/synthesis/${DESIGN}_p${PERIOD}"
file mkdir $OUT

set LIB "/usr/local/synopsys/pdk/SAED32_EDK/lib/stdcell_rvt/db_nldm/saed32rvt_ss0p7v125c.db"
set_app_var target_library [list $LIB]
set_app_var link_library   [list "*" $LIB]

set V "$REPO/verilog"
if {$DESIGN eq "fp32"} {
    set TOP fpu
    set RTL_FILES [list $V/except.v $V/pre_norm.v $V/pre_norm_fmul.v $V/post_norm.v $V/primitives.v $V/fpu.v]
} elseif {$DESIGN eq "bf16"} {
    set TOP fpu_bf16_wrapper
    set RTL_FILES [list $V/bf16_addsub_native.v $V/bf16_mul_native.v $V/bf16_div_native.v $V/fpu_bf16_wrapper.v]
} else {
    error "DESIGN must be fp32 or bf16"
}
foreach f $RTL_FILES { if {![file exists $f]} { error "missing RTL: $f" } }

analyze -format verilog $RTL_FILES
elaborate $TOP
current_design $TOP
link
check_design > "$OUT/check_design.log"

create_clock -name clk -period $PERIOD -waveform [list 0 [expr {$PERIOD / 2.0}]] [get_ports clk]
set DATA_INPUTS [remove_from_collection [all_inputs] [get_ports clk]]
set_input_delay  0.1 -max -clock clk $DATA_INPUTS
set_output_delay 0.1 -max -clock clk [all_outputs]
set_clock_uncertainty 0.2 -setup [get_clocks clk]
set_clock_uncertainty 0.2 -hold  [get_clocks clk]

set t0 [clock seconds]
compile_ultra
set t1 [clock seconds]

report_qor                              > "$OUT/qor.log"
report_area -hierarchy                  > "$OUT/area.log"
report_timing -max_paths 20             > "$OUT/timing_setup.log"
report_timing -delay_type min -max_paths 5 > "$OUT/timing_hold.log"
report_constraint -all_violators        > "$OUT/violators.log"
report_power -hierarchy                 > "$OUT/power_dc.log"
report_reference -hierarchy             > "$OUT/reference.log"

change_names -rules verilog -hierarchy
write -format verilog -hierarchy -output "$OUT/${TOP}_netlist.v"
write_sdc "$OUT/${TOP}.sdc"
write_sdf "$OUT/${TOP}.sdf"

set fh [open "$OUT/compile_time.txt" w]
puts $fh "compile_ultra seconds: [expr {$t1 - $t0}]"
close $fh
puts "SYNTHESIS COMPLETE: $DESIGN at $PERIOD ns -> $OUT"
exit
