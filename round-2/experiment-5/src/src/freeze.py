"""Freeze guard: frozen JSON + its sha256 file + a git commit that predates the current run."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def sha256_file(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def write_frozen(p: Path, obj: dict, message: str) -> str:
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=1, sort_keys=True))
    h = sha256_file(p)
    hp = p.with_suffix(".sha256")
    hp.write_text(h + "\n")
    subprocess.run(["git", "-C", str(ROOT), "add", "-f", str(p), str(hp)], check=True)
    subprocess.run(["git", "-C", str(ROOT), "commit", "-q", "-m", message, "--", str(p), str(hp)], check=True)
    return h


def assert_frozen(p: Path) -> str:
    """Exit nonzero unless p exists, its sha256 matches p.sha256 and it was committed before now."""
    p = Path(p)
    hp = p.with_suffix(".sha256")
    if not p.exists() or not hp.exists():
        print(f"FREEZE GUARD: missing {p} or {hp}", file=sys.stderr)
        sys.exit(3)
    h = sha256_file(p)
    want = hp.read_text().strip()
    if h != want:
        print(f"FREEZE GUARD: hash mismatch {p}: {h} != {want}", file=sys.stderr)
        sys.exit(4)
    r = subprocess.run(["git", "-C", str(ROOT), "log", "-1", "--format=%ct", "--", str(p)], capture_output=True,
                       text=True)
    ct = int(r.stdout.strip() or 0)
    if not ct or ct > time.time():
        print(f"FREEZE GUARD: {p} not committed (or commit in the future)", file=sys.stderr)
        sys.exit(5)
    dirty = subprocess.run(["git", "-C", str(ROOT), "diff", "--quiet", "HEAD", "--", str(p)]).returncode
    if dirty:
        print(f"FREEZE GUARD: {p} differs from its commit", file=sys.stderr)
        sys.exit(6)
    print(f"FREEZE GUARD OK: {p.name} sha256={h} committed_at={ct}")
    return h
