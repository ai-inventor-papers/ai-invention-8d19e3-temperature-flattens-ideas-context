"""Activation cache stored as row-split parts (each < 100 MB) so it fits the repository file-size limit.

acts/baseline_{task}_part_001.npy, _part_002.npy, ... hold consecutive blocks of ROWS_PER_PART samples of the
[n_samples, 10 positions, 37 layers, 2048] float16 cache. SplitActs reads them lazily (memory-mapped) and supports
the indexing patterns used in this repo: acts[:, ...] (all samples) and acts[i, ...] (one sample).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

ROWS_PER_PART = 50  # 50 x 10 x 37 x 2048 x 2 bytes = 75.8 MB per part


def part_paths(acts_dir: Path | str, task: str) -> list[Path]:
    return sorted(Path(acts_dir).glob(f"baseline_{task}_part_*.npy"))


def save_split(arr: np.ndarray, acts_dir: Path | str, task: str) -> list[Path]:
    acts_dir = Path(acts_dir)
    for old in part_paths(acts_dir, task):
        old.unlink()
    out = []
    for k, start in enumerate(range(0, arr.shape[0], ROWS_PER_PART), 1):
        p = acts_dir / f"baseline_{task}_part_{k:03d}.npy"
        np.save(p, np.ascontiguousarray(arr[start:start + ROWS_PER_PART]))
        out.append(p)
    return out


class SplitActs:
    def __init__(self, acts_dir: Path | str, task: str):
        self.parts = [np.load(p, mmap_mode="r") for p in part_paths(acts_dir, task)]
        if not self.parts:
            raise FileNotFoundError(f"no activation parts for {task} in {acts_dir}")
        self.offsets = np.cumsum([0] + [p.shape[0] for p in self.parts])
        self.shape = (int(self.offsets[-1]),) + self.parts[0].shape[1:]

    def __len__(self) -> int:
        return self.shape[0]

    def __getitem__(self, key):
        key = key if isinstance(key, tuple) else (key,)
        first, rest = key[0], key[1:]
        if isinstance(first, (int, np.integer)):
            i = int(first) % self.shape[0]
            k = int(np.searchsorted(self.offsets, i, side="right") - 1)
            return self.parts[k][(i - self.offsets[k],) + rest]
        if first == slice(None):
            return np.concatenate([p[(slice(None),) + rest] for p in self.parts], axis=0)
        rows = np.arange(self.shape[0])[first]
        return np.stack([self[(int(r),) + rest] for r in rows], axis=0)


def load_acts(acts_dir: Path | str, task: str) -> SplitActs:
    return SplitActs(acts_dir, task)
