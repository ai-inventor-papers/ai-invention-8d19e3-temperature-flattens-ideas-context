#!/usr/bin/env bash
# Post-sweep chain: judge (set A on sweep + audit sample) -> select -> held-out -> judge (new held-out programs) -> analyze
set -u
cd "$(dirname "$0")"
until grep -q "EXIT" logs/stage_sweep2.out; do sleep 15; done
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
.venv/bin/python method.py judge > logs/stage_judge1.out 2>&1; echo "judge1 $?"
.venv/bin/python method.py select > logs/stage_select.out 2>&1; echo "select $?"
.venv/bin/python method.py heldout --batch 200 > logs/stage_heldout.out 2>&1; echo "heldout $?"
.venv/bin/python method.py judge > logs/stage_judge2.out 2>&1; echo "judge2 $?"
.venv/bin/python method.py analyze > logs/stage_analyze.out 2>&1; echo "analyze $?"
echo "POST DONE"
