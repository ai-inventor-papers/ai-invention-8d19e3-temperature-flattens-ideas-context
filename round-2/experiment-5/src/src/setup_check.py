#!/usr/bin/env python3
"""STEP 0: input integrity. sha256 of every copied input, prompt byte-equality vs stored prompt_text and ids,
suffix identity, v1 fixtures + oracle tests, relabel 200 random stored generations (must be 100% equal)."""
from __future__ import annotations

import hashlib
import json
import random
import subprocess
import sys
from pathlib import Path

from loguru import logger

sys.path.insert(0, str(Path(__file__).resolve().parent))
from classify import classify_text  # noqa: E402
from protocol import MODEL, ROOT, TASK_KIND, TASKS  # noqa: E402
from protocol_ext import user_message  # noqa: E402

logger.remove()
logger.add(sys.stdout, level="INFO", format="{time:HH:mm:ss}|{level:<7}|{message}")
logger.add(ROOT / "logs" / "setup_check.log", rotation="30 MB", level="DEBUG")
SRC_E2 = "iter_1/gen_art/gen_art_experiment_2"
SRC_E3 = "iter_1/gen_art/gen_art_experiment_3"


def load_jsonl(p: Path) -> list[dict]:
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()]


@logger.catch(reraise=True)
def main() -> None:
    from transformers import AutoTokenizer

    out: dict = {"copied_from": {"ban_arm": SRC_E2, "influence_arm": SRC_E3}}
    files = sorted([p for p in (ROOT / "data" / "gen").rglob("*.jsonl")] + [p for p in (ROOT / "data" / "labels").rglob("*.jsonl")]
                   + [ROOT / "data" / "ban_plan.json", ROOT / "data" / "ban_plan_meta.json"]
                   + [ROOT / "src" / f"{m}.py" for m in ("protocol", "classify", "label", "oracle", "oracle_harness",
                                                         "activations", "geometry", "generate", "engine", "acts_io")]
                   + sorted((ROOT / "tests").glob("test_classifier.py")) + sorted((ROOT / "tests").glob("test_oracle.py")))
    out["sha256"] = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    (ROOT / "manifest_inputs.json").write_text(json.dumps(out, indent=1))
    logger.info(f"hashed {len(files)} input files")

    tok = AutoTokenizer.from_pretrained(MODEL)
    plan = json.loads((ROOT / "data" / "ban_plan.json").read_text())
    n_ok = n_all = 0
    suffixes = set()
    for t in TASKS:
        for p in sorted((ROOT / "data" / "gen" / t).glob("*.jsonl")):
            cond = p.stem
            r = json.loads(p.read_text().splitlines()[0])
            banned = plan[t].get(cond, []) if cond in plan[t] else []
            um = user_message(t, cond, banned)
            text = tok.apply_chat_template([{"role": "user", "content": um}], tokenize=False, add_generation_prompt=True)
            ids = tok(text, add_special_tokens=False)["input_ids"]
            ok = text == r["prompt_text"] and ids == r["prompt_token_ids"]
            n_all += 1
            n_ok += ok
            if not ok:
                logger.error(f"prompt mismatch {t}/{cond}: {um!r} vs {r['user_message']!r}")
            suffixes.add(tuple(ids[-5:]))
    out["prompt_byte_equal"] = f"{n_ok}/{n_all}"
    suf = list(suffixes)
    out["suffix_ids"] = [list(s) for s in suf]
    out["suffix_tokens"] = [[tok.decode([i]) for i in s] for s in suf]
    logger.info(f"prompt byte-equality {n_ok}/{n_all}; distinct 5-token suffixes={len(suf)} {out['suffix_tokens']}")
    assert n_ok == n_all and len(suf) == 1
    assert tok.decode(list(suf[0])) == "<|im_end|>\n<|im_start|>assistant\n", tok.decode(list(suf[0]))

    for test in ("tests/test_classifier.py", "tests/test_oracle.py", "tests/test_classifier_t4.py"):
        cmd = ([sys.executable, test] if test.endswith("test_oracle.py") else  # script-style test (exit code = #failures)
               [sys.executable, "-m", "pytest", "-q", "-o", "addopts=", "--noconftest", "-p", "no:cacheprovider", test])
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
        out[f"pytest_{Path(test).stem}"] = r.stdout.strip().splitlines()[-1]
        logger.info(f"{test}: {out[f'pytest_{Path(test).stem}']}")
        assert r.returncode == 0, r.stdout[-2000:]

    rng = random.Random(0)
    pool = []
    for t in TASKS:
        for p in sorted((ROOT / "data" / "gen" / t).glob("*.jsonl")):
            if p.stem == "comention":
                continue
            lab = ROOT / "data" / "labels" / t / p.name
            if lab.exists():
                pool += [(t, p, i) for i in range(len(lab.read_text().splitlines()))]
    pick = rng.sample(pool, 200)
    agree = 0
    cache: dict = {}
    for t, p, i in pick:
        if p not in cache:
            cache[p] = (load_jsonl(p), load_jsonl(ROOT / "data" / "labels" / t / p.name))
        g, l = cache[p]
        assert g[i]["id"] == l[i]["id"]
        agree += classify_text(g[i]["output_text"], TASK_KIND[t])["label"] == l[i]["label"]
    out["relabel_agreement"] = f"{agree}/200"
    logger.info(f"relabel agreement {agree}/200")
    (ROOT / "manifest_inputs.json").write_text(json.dumps(out, indent=1))
    assert agree == 200


if __name__ == "__main__":
    main()
