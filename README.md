# CS220 Team 5 — BF16 Floating-Point Unit

## Project Overview

**Baseline:** the OpenCores single-precision FPU by Rudolf Usselmann (`verilog/fpu.v` and submodules). It has a 4-stage pipeline (one operation per cycle, result four cycles later) with add, sub, mul, div, i2f and f2i, and all four IEEE rounding modes.

**Optimization:** a native bfloat16 FPU (`verilog/fpu_bf16_wrapper.v`, `bf16_addsub_native.v`, `bf16_mul_native.v`, `bf16_div_native.v`). It keeps the same interface style and 4-cycle latency, has an 8-bit significand datapath, and does not instantiate the FP32 core.

## Team Members

- Deepthi Dayanand
- Utkarsh Raj
- Scott Peterson

## Baseline RTL changes

The FP32 baseline RTL is the original OpenCores code. The only edit wraps two simulation-only debug `$display` blocks (`verilog/fpu.v`, `verilog/post_norm.v`) in `` `ifdef FPU_LEGACY_TEST_DEBUG ``, so they stay silent by default. No functional logic was changed.

## Repository layout

| Path | Contents |
|---|---|
| `verilog/` | FP32 baseline RTL and native BF16 RTL |
| `test_bench/test_fp32_baseline.v` | FP32 baseline testbench: streams vectors one per cycle and checks `out`, `inf`, `qnan`, `zero` and `div_by_zero`. Used for both RTL and netlist simulation |
| `test_vectors/fp32_golden_model.py` | Exact (rational-arithmetic) IEEE-754 binary32 reference model and vector generator |
| `test_vectors/fp32_baseline_vectors.hex` | 12 directed corner cases plus 16 random-constrained cases (every op × rounding mode) |
| `test_vectors/fp32_regression.hex` | 4,000-case regression: 2,000 constrained random plus 2,000 full-range cases (subnormals, overflow, underflow) |
| `test_bench/test_bf16_*.v`, `test_vectors/bf16_*.py` | BF16 testbenches, exact BF16 oracle and algorithm models |
| `synthesis/compile_sweep.tcl` | Design Compiler script; `DESIGN=fp32\|bf16`, `PERIOD=<ns>` |
| `synthesis/compile_bf16_*.tcl`, `synthesis/*_reports/` | Earlier BF16 synthesis runs at 2 ns |
| `power/ptpx.tcl` | PrimeTime PX averaged power from the netlist-simulation VCD |
| `scripts/` | One-command wrappers for each step below |

## Reproducing the results

All synthesis uses SAED32 RVT at the SS corner (0.7 V, 125 °C), with 0.1 ns input and output delay and 0.2 ns clock uncertainty. Only the clock period differs between runs. Run every command from the repository root.

### 1. RTL simulation (FP32 baseline)
```bash
bash scripts/rtl_sim.sh              # 28 corner + random-constrained cases
bash scripts/rtl_sim.sh regression   # + 4,000-case regression
```
This uses VCS when available and falls back to Icarus Verilog. Expected output: `28 / 28` and `4000 / 4000` checks passed.

### 2. Synthesis at a clock period that meets timing
```bash
DESIGN=fp32 bash scripts/syn.sh 40 36 32   # runs in parallel with nohup
DESIGN=bf16 bash scripts/syn.sh 10 9 8
```
Outputs go to `synthesis/<design>_p<period>/`: QoR, area, setup and hold timing, violators, DC power, netlist, SDC and SDF. The reported fmax is the shortest period with non-negative slack (course guideline: tighten the clock until slack is near zero, without a large jump in area).

### 3. Gate-level netlist simulation
```bash
DESIGN=fp32 PERIOD=40 bash scripts/netlist_sim.sh    # SDF back-annotated
DESIGN=fp32 PERIOD=40 MODE=zero bash scripts/netlist_sim.sh   # zero-delay functional check
```
This runs the same vectors as RTL simulation on the synthesized netlist and writes `sim/<design>_p<period>/netlist.vcd` for power analysis. If the SAED32 cell models live somewhere else, set `SAED32_V=<path to .v>`.

### 4. PrimeTime power
```bash
DESIGN=fp32 PERIOD=40 bash scripts/ptpx.sh
```
Reports go to `synthesis/<design>_p<period>/ptpx/`.

### 5. Collect numbers
```bash
bash scripts/summary.sh
```

### BF16 suites
```bash
bash run_bf16.sh golden      # exact-oracle vectors through the BF16 FPU
bash run_bf16.sh accuracy    # BF16 vs FP32 error statistics
```
