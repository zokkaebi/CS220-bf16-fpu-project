#!/usr/bin/env bash
# Print the numbers to paste back for the report / slides.
#   bash scripts/summary.sh
cd "$(dirname "$0")/.."
for d in synthesis/fp32_p* synthesis/bf16_p*; do
  [ -f "$d/qor.log" ] || continue
  echo "=================== $d"
  grep -E "Levels of Logic|Critical Path (Length|Slack)|Total Negative Slack|Worst Hold Violation|Leaf Cell Count|Sequential Cell Count|^ *Cell Area|^ *Design Area|Overall Compile" "$d/qor.log" | sed 's/^ */  /'
  cat "$d/compile_time.txt" 2>/dev/null | sed 's/^/  /'
  grep -m2 -E "Startpoint|Endpoint" "$d/timing_setup.log" | sed 's/^ */  /'
  echo "  -- DC power (switch uW, internal uW, leakage pW, total uW):"
  grep -E "^ *(fpu|fpu_bf16_wrapper) +[0-9]" "$d/power_dc.log" | head -1 | sed 's/^ */    /'
  if [ -f "$d/ptpx/power.log" ]; then
    echo "  -- PrimeTime power:"; grep -E "Net Switching Power|Cell Internal Power|Cell Leakage Power|Total Power" "$d/ptpx/power.log" | sed 's/^ */    /'
    echo "  -- not-annotated nets:"; grep -ciE "not annotated|^ *[a-z_]" "$d/ptpx/switching_not_annotated.log" | sed 's/^/    /'
  fi
done
for s in sim/*_p*; do
  [ -d "$s" ] || continue
  echo "=================== $s"; grep -hE "RESULT|PASSED|MISMATCH|FAIL" $s/*.log 2>/dev/null | head -6 | sed 's/^/  /'
done
