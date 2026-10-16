#!/bin/bash
# chain 2 (actually run): waits for gemma screen_a and the Qwen vectors stage, then runs every remaining GPU stage.
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
cd "$(dirname "$0")"
while kill -0 "$(cat logs/gemma_a.pid)" 2>/dev/null; do sleep 10; done
while kill -0 "$(cat logs/vectors.pid)" 2>/dev/null; do sleep 10; done
set -e
P=.venv/bin/python
$P src/steer_qwen.py freeze > logs/freeze.out 2>&1
$P src/steer_qwen.py calib --batch 200 > logs/calib.out 2>&1
$P src/steer_qwen.py freeze2 > logs/freeze2.out 2>&1
$P src/steer_qwen.py main --batch 200 > logs/main.out 2>&1
G="--batch 75 --max_new 768"
$P src/gemma.py screen_b --nf 20 --nban 50 $G > logs/gemma_screen_b.out 2>&1
$P src/gemma.py geometry > logs/gemma_geometry.out 2>&1
$P src/gemma.py confirm --nconf 50 $G > logs/gemma_confirm.out 2>&1
$P src/gemma.py confirm_states > logs/gemma_confirm_states.out 2>&1
$P src/gemma.py temp --ntemp 40 $G > logs/gemma_temp.out 2>&1
$P src/gemma.py transplant --ntr 30 $G > logs/gemma_transplant.out 2>&1
echo CHAIN2_DONE > logs/chain2.done
