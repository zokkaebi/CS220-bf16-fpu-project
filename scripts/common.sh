# Shared settings for the Bender scripts. Source, don't run.
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"
DESIGN="${DESIGN:-fp32}"
PERIOD="${PERIOD:-40}"
case "$DESIGN" in
  fp32) TOP=fpu; TB=test_fp32_baseline
        TB_FILE=test_bench/test_fp32_baseline.v
        RTL="verilog/except.v verilog/pre_norm.v verilog/pre_norm_fmul.v verilog/post_norm.v verilog/primitives.v verilog/fpu.v" ;;
  bf16) TOP=fpu_bf16_wrapper; TB=test_bf16_streaming_golden
        TB_FILE=test_bench/test_bf16_streaming_golden.v
        RTL="verilog/bf16_addsub_native.v verilog/bf16_mul_native.v verilog/bf16_div_native.v verilog/fpu_bf16_wrapper.v" ;;
  *) echo "DESIGN must be fp32 or bf16" >&2; exit 1 ;;
esac
SYN_DIR="synthesis/${DESIGN}_p${PERIOD}"
SIM_DIR="sim/${DESIGN}_p${PERIOD}"
# SAED32 RVT cell simulation models (needed for gate-level simulation).
SAED32_V="${SAED32_V:-/usr/local/synopsys/pdk/SAED32_EDK/lib/stdcell_rvt/verilog/saed32nm.v}"
