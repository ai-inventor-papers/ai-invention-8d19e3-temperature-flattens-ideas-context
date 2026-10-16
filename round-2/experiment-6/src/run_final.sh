#!/bin/bash
# final analysis chain (actually run after the GPU chains): analyses -> verdicts -> figures -> output -> verify
set -e
cd "$(dirname "$0")"
P=.venv/bin/python
$P src/analyze_qwen.py > logs/analyze_qwen.out 2>&1
$P src/analyze_gemma.py > logs/analyze_gemma.out 2>&1
$P src/verdicts.py > logs/verdicts.out 2>&1
$P src/figures.py > logs/figures.out 2>&1
$P method.py output > logs/output.out 2>&1
$P verify.py > logs/verify.out 2>&1
# schema validation + full/mini/preview variants use the AI-Inventor aii-json skill (set AII_JSON_SKILL_DIR)
if [ -n "${AII_JSON_SKILL_DIR:-}" ]; then
  PYJ=$AII_JSON_SKILL_DIR/../.ability_client_venv/bin/python
  $PYJ $AII_JSON_SKILL_DIR/scripts/aii_json_validate_schema.py --format exp_gen_sol_out --file "$(pwd)/method_out.json"
  $PYJ $AII_JSON_SKILL_DIR/scripts/aii_json_format_mini_preview.py --input "$(pwd)/method_out.json"
fi
ls -lh method_out.json full_method_out.json mini_method_out.json preview_method_out.json
