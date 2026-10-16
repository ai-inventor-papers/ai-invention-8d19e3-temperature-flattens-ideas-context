#!/usr/bin/env python3
"""CODE-STOP CHECK (CPU): v1 label of the full BA baseline text vs the text truncated after the first closed
```python block. Agreement >= 0.97 keeps CodeStop for every new generation. Also checks the Qwen tokenizer gives
identical prompt ids with and without add_special_tokens (the engine now passes False for gemma's BOS)."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from classify import classify_text  # noqa: E402
from common import BA, QWEN, RESULTS, read_jsonl, write_json  # noqa: E402
from engine import PY_CLOSED_RE, render  # noqa: E402
from protocol import TASK_KIND, user_message  # noqa: E402

out = {}
for t in ("T1", "T2"):
    rows = read_jsonl(BA / "data/gen" / t / "baseline.jsonl")
    agree = 0
    for r in rows:
        txt = r["output_text"]
        m = PY_CLOSED_RE.search(txt)
        cut = txt[:m.end()] if m else txt
        agree += classify_text(txt, TASK_KIND[t])["label"] == classify_text(cut, TASK_KIND[t])["label"]
    out[t] = dict(n=len(rows), agreement=agree / len(rows))
out["keep_codestop"] = all(v["agreement"] >= 0.97 for k, v in out.items() if k.startswith("T"))
from transformers import AutoTokenizer  # noqa: E402
tok = AutoTokenizer.from_pretrained(QWEN)
s = render(tok, user_message("T1", "baseline"))
out["qwen_ids_identical_with_without_special"] = tok(s)["input_ids"] == tok(s, add_special_tokens=False)["input_ids"]
write_json(RESULTS / "codestop_check.json", out)
print(json.dumps(out))
