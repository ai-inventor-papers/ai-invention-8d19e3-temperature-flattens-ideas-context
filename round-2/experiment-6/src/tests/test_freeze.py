#!/usr/bin/env python3
"""Testing plan item 6: a missing or tampered frozen file makes the confirmation/main guard exit non-zero, and the
hash returned at run start equals the .sha256 sidecar."""
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from common import RESULTS, require_frozen  # noqa: E402

res = {}
with tempfile.TemporaryDirectory(dir=ROOT / "data") as td:
    td = Path(td)
    for name in ("frozen_selector_qwen.json", "frozen_gemma_bans.json"):
        src = RESULTS / name
        if not src.exists():
            continue
        h = require_frozen(src)
        res[name + "_hash_matches_sidecar"] = h == (RESULTS / (name + ".sha256")).read_text().split()[0]
        try:
            require_frozen(td / name)  # missing
            res[name + "_missing_exits"] = False
        except SystemExit:
            res[name + "_missing_exits"] = True
        shutil.copy(src, td / name)
        shutil.copy(RESULTS / (name + ".sha256"), td / (name + ".sha256"))
        (td / name).write_text((td / name).read_text().replace('"', "'", 1))  # tamper
        try:
            require_frozen(td / name)
            res[name + "_tampered_exits"] = False
        except SystemExit:
            res[name + "_tampered_exits"] = True
print(res)
assert all(res.values())
print("FREEZE GUARD TESTS PASS")
