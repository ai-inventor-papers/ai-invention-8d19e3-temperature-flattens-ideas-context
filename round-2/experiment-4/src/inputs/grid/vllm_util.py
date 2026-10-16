"""vLLM helpers (only imported inside vLLM processes; never alongside HF models)."""

from __future__ import annotations

import time

from loguru import logger

from common import MODEL


def make_llm(gpu_util: float = 0.85):
    from vllm import LLM
    t0 = time.time()
    llm = LLM(model=MODEL, dtype="bfloat16", gpu_memory_utilization=gpu_util, enable_prefix_caching=True,
              max_model_len=4096, seed=0, max_num_seqs=512, enforce_eager=True)
    logger.info(f"vLLM loaded in {time.time() - t0:.1f}s")
    return llm


def sp(temperature: float, top_k: int, max_tokens: int, seed: int | None, n: int = 1, logprobs: int | None = None):
    from vllm import SamplingParams
    kw = dict(temperature=temperature, top_p=1.0, min_p=0.0, max_tokens=max_tokens, n=n)
    if temperature > 0:
        kw["top_k"] = top_k if top_k > 0 else -1
        kw["seed"] = seed
    if logprobs is not None:
        kw["logprobs"] = logprobs
    return SamplingParams(**kw)


def generate(llm, prompt_ids: list[list[int]], params: list, desc: str = "") -> list:
    from vllm.inputs import TokensPrompt
    t0 = time.time()
    outs = llm.generate([TokensPrompt(prompt_token_ids=p) for p in prompt_ids], params, use_tqdm=False)
    ntok = sum(len(o.token_ids) for out in outs for o in out.outputs)
    dt = time.time() - t0
    logger.info(f"[{desc}] {len(prompt_ids)} reqs, {ntok} gen tokens in {dt:.1f}s ({ntok / max(dt, 1e-9):.0f} tok/s)")
    return outs
