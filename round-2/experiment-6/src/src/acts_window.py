"""Teacher-forced commitment-window activations (shared by Qwen step B2 and gemma step C2) + CV probe band.

Window = output tokens [c, c+16] where c = first idea-lexicon token (BA activations.commit_pos); fallback
(no lexicon hit, or c >= 600) = generated tokens 1..32. hidden_states[l] for l = 1..L-1 (the last HF hidden
state is post-final-norm and is excluded). Per sample we keep the window mean per layer and the median token
norm in the window per layer (the steering scale unit).
"""
from __future__ import annotations

import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import torch
from loguru import logger

import activations as ba_acts


def commit_window(tok, task: str, text: str, out_ids: list[int]) -> tuple[int, int, bool, int]:
    c, fb = ba_acts.commit_pos(tok, dict(task=task, output_text=text, output_token_ids=out_ids))
    no = len(out_ids)
    if fb or no == 0:
        return 0, min(31, max(no - 1, 0)), True, c
    return c, min(c + ba_acts.WIN, no - 1), False, c


@torch.no_grad()
def window_acts(model, tok, recs: list[dict], n_layers: int, bs: int = 24) -> dict:
    """recs: dicts with task, prompt_ids, out_ids, text. Returns window [n, n_layers-1, d] f16, norms, fallback."""
    n = len(recs)
    d = model.config.hidden_size
    L = n_layers - 1  # hidden_states[1..n_layers-1]
    win = np.zeros((n, L, d), np.float16)
    nrm = np.zeros((n, L), np.float32)
    fb = np.zeros(n, bool)
    cpos = np.zeros(n, np.int32)
    seqs = []
    for i, r in enumerate(recs):
        w0, w1, f, c = commit_window(tok, r["task"], r["text"], r["out_ids"])
        fb[i], cpos[i] = f, c
        ids = list(r["prompt_ids"]) + list(r["out_ids"][: w1 + 1])
        npr = len(r["prompt_ids"])
        if len(ids) <= npr:
            ids, w0, w1 = list(r["prompt_ids"]), -1, -1
        seqs.append(dict(i=i, ids=ids, np=npr, w=(w0, w1)))
    order = sorted(range(n), key=lambda k: len(seqs[k]["ids"]))
    pad = tok.pad_token_id if tok.pad_token_id is not None else 0
    k = 0
    while k < n:
        batch = [seqs[j] for j in order[k:k + bs]]
        T = max(len(s["ids"]) for s in batch)
        inp = torch.full((len(batch), T), pad, dtype=torch.long)
        att = torch.zeros((len(batch), T), dtype=torch.long)
        for b, s in enumerate(batch):  # right padding: positions are absolute from 0
            inp[b, : len(s["ids"])] = torch.tensor(s["ids"])
            att[b, : len(s["ids"])] = 1
        try:
            out = model.model(input_ids=inp.cuda(), attention_mask=att.cuda(), output_hidden_states=True)
        except torch.cuda.OutOfMemoryError:
            torch.cuda.empty_cache()
            bs = max(1, bs // 2)
            logger.warning(f"acts OOM -> batch {bs}")
            continue
        hs = torch.stack(out.hidden_states[1:n_layers], 1)  # [B, L, T, d]
        for b, s in enumerate(batch):
            w0, w1 = s["w"]
            a0 = s["np"] + w0 if w0 >= 0 else len(s["ids"]) - 1
            a1 = s["np"] + w1 if w1 >= 0 else len(s["ids"]) - 1
            seg = hs[b, :, a0:a1 + 1].float()
            win[s["i"]] = seg.mean(1).cpu().numpy().astype(np.float16)
            nrm[s["i"]] = seg.norm(dim=-1).median(dim=1).values.cpu().numpy()
        del out, hs
        k += len(batch)
    return dict(window=win, norm=nrm, fallback=fb, c_pos=cpos)


def _init_worker():
    import os
    for k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ[k] = "1"
    try:
        from threadpoolctl import threadpool_limits
        threadpool_limits(1)
    except ImportError:
        pass
    os.nice(10)  # never starve the GPU generation process (its HF loop is CPU-launch-bound)


def _probe_layer(args):
    import warnings

    from sklearn.decomposition import PCA
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import balanced_accuracy_score
    from sklearn.model_selection import StratifiedKFold
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    warnings.filterwarnings("ignore")
    X, y, n_shuf, seed = args
    rng = np.random.default_rng(seed)
    res = {}
    for C in (0.01, 0.1, 1.0):
        def cv(yy):
            skf = StratifiedKFold(5, shuffle=True, random_state=0)
            pred = np.empty(len(yy), dtype=object)
            for tr, te in skf.split(X, yy):
                clf = make_pipeline(StandardScaler(), PCA(min(128, len(tr) - 1), random_state=0),
                                    LogisticRegression(C=C, class_weight="balanced", max_iter=300))
                clf.fit(X[tr], yy[tr])
                pred[te] = clf.predict(X[te])
            return balanced_accuracy_score(yy, pred.astype(str))
        real = cv(y)
        shuf = float(np.mean([cv(rng.permutation(y)) for _ in range(n_shuf)]))
        res[C] = (real, shuf)
    bestC = max(res, key=lambda c: res[c][0])
    return dict(C=bestC, acc=res[bestC][0], shuffled=res[bestC][1], gain=res[bestC][0] - res[bestC][1],
                all={str(c): v for c, v in res.items()})


def probe_curve(X_by_task: dict, y_by_task: dict, n_layers: int, workers: int = 3, n_shuf: int = 5) -> dict:
    """X_by_task[t]: [n, L, d]; y: labels (classes with < 10 samples -> 'rare'). 5-fold CV balanced accuracy vs
    within-task shuffled labels, per layer; PCA(128) inside each fold for speed."""
    jobs, keys = [], []
    for t, X in X_by_task.items():
        y = np.array(y_by_task[t], dtype=object)
        cnt = {c: int((y == c).sum()) for c in set(y)}
        y = np.array([c if cnt[c] >= 10 else "rare" for c in y], dtype=object)
        if (y == "rare").sum() < 5:
            y = np.array([c if c != "rare" else max(cnt, key=cnt.get) for c in y], dtype=object)
        for l in range(X.shape[1]):
            jobs.append((X[:, l].astype(np.float32), y.astype(str), n_shuf, 100 + l))
            keys.append((t, l + 1))
    with ProcessPoolExecutor(max_workers=workers, mp_context=mp.get_context("spawn"), initializer=_init_worker) as ex:
        outs = list(ex.map(_probe_layer, jobs))
    curve = {}
    for (t, l), o in zip(keys, outs):
        curve.setdefault(t, {})[l] = o
    return curve


def choose_band(curve: dict, n_layers: int) -> tuple[list[int], dict]:
    layers = sorted(next(iter(curve.values())).keys())
    mean_gain = {l: float(np.mean([curve[t][l]["gain"] for t in curve])) for l in layers}
    best, bl = -1e9, None
    for l in layers[:-2]:
        g = np.mean([mean_gain[l], mean_gain[l + 1], mean_gain[l + 2]])
        if g > best:
            best, bl = g, l
    return [bl, bl + 1, bl + 2], dict(mean_gain=mean_gain, band_gain=float(best))
