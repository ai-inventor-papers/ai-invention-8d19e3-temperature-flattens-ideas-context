"""Check that every reader of the split activation cache works and reproduces stored results."""
import json
import multiprocessing as mp
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from src.acts_io import load_acts  # noqa: E402
from src.common import ACTS, setup_logging  # noqa: E402


def main() -> None:
    setup_logging("test_acts_split")
    import method
    from src.probes import probe_layer
    ctx = method.load_ctx()
    y, tasks, _ = method._probe_labels(ctx)
    with ProcessPoolExecutor(max_workers=1, mp_context=mp.get_context("spawn")) as ex:
        r = ex.submit(probe_layer, str(ACTS), 30, y.tolist(), tasks.tolist()).result()
    ref = json.loads((ROOT / "results/probe_curve.json").read_text())["layers"][30]
    print("probe L30 bal", round(r["bal_acc_pooled"], 4), "stored", round(ref["bal_acc_pooled"], 4))
    assert abs(r["bal_acc_pooled"] - ref["bal_acc_pooled"]) < 1e-9
    from src import analysis as A
    C = A.ctx()
    print("capture probes fit at layers", sorted(A.fit_capture_probes(C)))
    T = A.build_table(include_ho=True)
    surv = json.loads((ROOT / "results/results.json").read_text())["survival"]
    print(A.make_figures(T, C, surv, ROOT / "figs"))
    acts = {t: load_acts(ACTS, t) for t in ("T1", "T3")}
    med = float(np.median(np.concatenate([np.linalg.norm(acts[t][:, 1:9, 30, :].astype(np.float32), axis=-1).ravel()
                                          for t in ("T1", "T3")])))
    print("median norm L30", round(med, 3), "stored", round(C["median_norm"]["30"], 3))
    assert abs(med - C["median_norm"]["30"]) < 1e-3
    print("ALL OK")


if __name__ == "__main__":
    main()
