"""GPU generation runner (one HF engine for every condition of a model) + concurrent v1/oracle scoring.

A job = one setting on one task: {task, setting, family, user_message, seeds, T, topk, iv, code_stop}.
Rows of different settings share batches (common random numbers through the per-seed uniforms of SeededSampler).
Generations append to data/gens/<model>/<task>/<setting>.jsonl (resumable: finished seeds are skipped) and are
scored in a background thread (rule classifier v1 + sandboxed oracle) into data/scored/<model>/<task>/<setting>.jsonl.
"""
from __future__ import annotations

import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

from loguru import logger

sys.path.insert(0, str(Path(__file__).resolve().parent))
from classify import CLASSIFIER_VERSION, classifier_hash, classify_text  # noqa: E402
from common import GENS, MODEL_TAG, SCORED, append_jsonl, read_jsonl  # noqa: E402
from oracle import run_many  # noqa: E402
from protocol import TASK_KIND  # noqa: E402

CLS_TAG = None


def oracle_status(o: dict) -> str:
    if o.get("passed"):
        return "pass"
    if o.get("error") == "wall_timeout" or "Timeout" in str(o.get("error", "")):
        return "timeout"
    if not o.get("callable"):
        return "not_callable"
    return "fail"


def score_records(recs: list[dict], workers: int = 3) -> list[dict]:
    """v1 label + oracle (code-only extraction by classify.extract_code)."""
    global CLS_TAG
    if CLS_TAG is None:
        CLS_TAG = f"{CLASSIFIER_VERSION}:{classifier_hash()}"
    rows, items = [], []
    for r in recs:
        c = classify_text(r["text"], TASK_KIND[r["task"]])
        rows.append(dict(id=r["id"], model=r["model"], task=r["task"], setting=r["setting"], family=r["family"],
                         seed=r["seed"], label=c["label"], multi=c["multi"], is_python=c["is_python"],
                         oracle_eligible=c["oracle_eligible"], ntoks=r["ntoks"], hit_max=r["hit_max"],
                         classifier=CLS_TAG))
        items.append((c["code"] if c["oracle_eligible"] and c["code"] else "", r["task"]))
    res = run_many(items, workers=workers)
    for row, o in zip(rows, res):
        row["oracle_status"] = oracle_status(o)
        row["oracle_pass"] = bool(o.get("passed"))
        row["pass_frac"] = float(o.get("pass_frac") or 0.0)
        row["oracle_callable"] = bool(o.get("callable"))
    return rows


def gens_path(model: str, task: str, setting: str) -> Path:
    return GENS / MODEL_TAG[model] / task / f"{setting}.jsonl"


def scored_path(model: str, task: str, setting: str) -> Path:
    return SCORED / MODEL_TAG[model] / task / f"{setting}.jsonl"


def load_scored(model: str, task: str, setting: str) -> list[dict]:
    return read_jsonl(scored_path(model, task, setting))


class Runner:
    def __init__(self, model_id: str, batch: int = 160, max_new: int = 768, window: int = 64,
                 eos_ids: tuple[int, ...] | None = None):
        self.model_id = model_id
        self.B = batch
        self.max_new = max_new
        self.window = window
        self.eos_ids = eos_ids
        self.tok = self.model = None
        self.pool = ThreadPoolExecutor(1)
        self.pending = []
        self.throughput: list[tuple[int, float]] = []

    def load(self):
        if self.model is None:
            from engine import Steerer, backtick_token_ids, load_model
            self.tok, self.model = load_model(self.model_id)
            self.ticks = backtick_token_ids(self.tok)
            self.steerer = Steerer(self.model, window=self.window, capture_layers=[])
            if self.eos_ids is None:
                ids = {self.tok.eos_token_id}
                for t in ("<|im_end|>", "<|endoftext|>", "<end_of_turn>", "<eos>"):
                    i = self.tok.convert_tokens_to_ids(t)
                    if isinstance(i, int) and i != self.tok.unk_token_id and i is not None:
                        ids.add(i)
                self.eos_ids = tuple(sorted(i for i in ids if i is not None))
            logger.info(f"loaded {self.model_id}; eos {self.eos_ids}; backtick tokens {len(self.ticks)}")
        return self.tok, self.model

    def run(self, jobs: list[dict], resolver: Callable[[str, dict | None], object], tag: str,
            score: bool = True) -> None:
        import torch
        from engine import Intervention, free, generate_batch
        model_tag = MODEL_TAG[self.model_id]
        todo = []
        for j in jobs:
            gp = gens_path(self.model_id, j["task"], j["setting"])
            have = {r["seed"] for r in read_jsonl(gp)}
            sp = scored_path(self.model_id, j["task"], j["setting"])
            sdone = {r["seed"] for r in read_jsonl(sp)}
            back = [r for r in read_jsonl(gp) if r["seed"] not in sdone]
            if back and score:
                logger.info(f"scoring backlog {j['task']}/{j['setting']}: {len(back)}")
                self.pending.append(self.pool.submit(self._score, back, sp))
            todo += [(j, s) for s in j["seeds"] if s not in have]
        logger.info(f"[{tag}] {len(todo)} generations to run over {len(jobs)} jobs (batch {self.B})")
        if not todo:
            self.wait()
            return
        self.load()
        # Batches never mix prompt-token lengths: left padding forces SDPA off its fast causal path (measured 3.2x
        # slower on this GPU). Rows of different settings with the same prompt length still share batches (CRN).
        from engine import render
        plen: dict = {}
        for j, _ in todo:
            if j["user_message"] not in plen:
                plen[j["user_message"]] = len(self.tok(render(self.tok, j["user_message"]),
                                                       add_special_tokens=False)["input_ids"])
        groups: dict = defaultdict(list)
        for it in todo:
            groups[plen[it[0]["user_message"]]].append(it)
        batches = []
        for _, items in sorted(groups.items()):
            nb = -(-len(items) // self.B)
            size = -(-len(items) // nb)
            batches += [items[i:i + size] for i in range(0, len(items), size)]
        ivcache: dict = {}
        t0 = time.time()
        k = done = 0
        bq = list(batches)
        while bq:
            batch = bq.pop(0)
            ivs = []
            for j, _ in batch:
                key = (j["task"], repr(j.get("iv")))
                if key not in ivcache:
                    ivcache[key] = resolver(j["task"], j.get("iv")) if j.get("iv") else Intervention()
                ivs.append(ivcache[key])
            try:
                res = generate_batch(self.tok, self.model, [j["user_message"] for j, _ in batch],
                                     [s for _, s in batch], [j.get("T", 0.7) for j, _ in batch],
                                     [j.get("topk", 0) for j, _ in batch], ivs,
                                     [j.get("code_stop", True) for j, _ in batch], self.steerer, self.ticks,
                                     max_new=self.max_new, eos_ids=self.eos_ids)
            except torch.cuda.OutOfMemoryError:
                free()
                self.B = max(8, self.B // 2)
                h = len(batch) // 2
                bq = [batch[:h], batch[h:]] + bq
                logger.warning(f"OOM -> batch {self.B}")
                continue
            steered_rows = sum(1 for iv in ivs if iv.kind != "none")
            if steered_rows and res["n_mod_calls"] == 0:
                raise RuntimeError("steered rows present but the hook never fired")
            by = defaultdict(list)
            for i, (j, s) in enumerate(batch):
                by[(j["task"], j["setting"])].append(dict(
                    id=f"{model_tag}|{j['task']}|{j['setting']}|{s}", model=model_tag, task=j["task"],
                    setting=j["setting"], family=j.get("family", ""), seed=s, T=j.get("T", 0.7),
                    topk=j.get("topk", 0), iv=j.get("iv"), user_message=j["user_message"], text=res["texts"][i],
                    output_token_ids=res["ids"][i], ntoks=res["ntoks"][i], hit_max=res["hit_max"][i],
                    batch_seconds=round(res["seconds"], 2), n_mod_calls=res["n_mod_calls"]))
            for (task, setting), recs in by.items():
                append_jsonl(gens_path(self.model_id, task, setting), recs)
                if score:
                    self.pending.append(self.pool.submit(self._score, recs,
                                                         scored_path(self.model_id, task, setting)))
            done += len(batch)
            el = time.time() - t0
            self.throughput.append((len(batch), res["seconds"]))
            logger.info(f"[{tag}] {done}/{len(todo)} gens; batch {len(batch)} in {res['seconds']:.0f}s "
                        f"({len(batch) / res['seconds'] * 60:.0f}/min); elapsed {el / 60:.1f} min; "
                        f"ETA {el / done * (len(todo) - done) / 60:.1f} min")
        free()

    def _score(self, recs: list[dict], out: Path) -> None:
        try:
            append_jsonl(out, score_records(recs))
        except Exception:
            logger.exception(f"scoring failed for {out}")
            raise

    def wait(self) -> None:
        for f in self.pending:
            f.result()
        self.pending = []
