#!/bin/bash
# chain 1: Qwen activations (B2) then gemma smoke (template + throughput)
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
cd "$(dirname "$0")"
.venv/bin/python src/steer_qwen.py acts > logs/acts.out 2>&1 || exit 1
.venv/bin/python src/gemma.py smoke --n 64 --batch 64 > logs/gemma_smoke.out 2>&1
