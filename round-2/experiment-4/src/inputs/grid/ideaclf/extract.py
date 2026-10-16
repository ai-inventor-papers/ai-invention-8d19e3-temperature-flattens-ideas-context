"""Code extraction, comment/docstring stripping and prose-declared idea detection.

All functions are pure and deterministic. Used both for full generations and for
truncated forking-path rollouts (partial mode).
"""

from __future__ import annotations

import ast
import re

FENCE_RE = re.compile(r"```[ \t]*([A-Za-z0-9_+\-]*)[^\n]*\n(.*?)(?:```|\Z)", re.S)

# ---------------------------------------------------------------------------
# Declared-idea lexicons (prose before the first code fence). Order inside a
# task does not matter: the EARLIEST match position in the prose wins.
# ---------------------------------------------------------------------------
PATH_LEXICON: list[tuple[str, str]] = [
    ("iddfs_idastar", r"iterative[\s-]+deepening|\biddfs\b|\bida\*|\bida[\s-]?star\b"),
    ("bidirectional", r"bi-?directional"),
    ("a_star", r"(?<![A-Za-z])a\*|\ba[\s-]star\b|\bastar\b"),
    ("greedy_best_first", r"(?:greedy\s+)?best[\s-]+first"),
    ("dijkstra", r"dijkstra|uniform[\s-]+cost"),
    ("bellman_ford_spfa", r"bellman[\s-]*ford|\bspfa\b|shortest\s+path\s+faster"),
    ("floyd_warshall", r"floyd|warshall"),
    ("bfs", r"\bbfs\b|breadth[\s-]+first"),
    ("dfs", r"\bdfs\b|depth[\s-]+first"),
]
SORT_LEXICON: list[tuple[str, str]] = [
    ("bubble", r"bubble"),
    ("selection", r"selection\s+sort"),
    ("insertion", r"insertion\s+sort"),
    ("merge", r"merge\s*sort"),
    ("quick", r"quick\s*sort"),
    ("heap", r"heap\s*sort"),
    ("shell", r"shell\s*sort"),
    ("counting", r"counting\s+sort"),
    ("radix", r"radix"),
    ("bucket", r"bucket\s+sort"),
    ("builtin_wrapper", r"\btim\s*sort\b|built-?in|\bsorted\(\)"),
]


def split_prose_code(text: str) -> tuple[str, list[tuple[str, str]]]:
    """Return (prose before the first fence, list of (lang, block_body))."""
    m = re.search(r"```", text)
    prose = text if m is None else text[: m.start()]
    blocks = [(lang.lower(), body) for lang, body in FENCE_RE.findall(text)]
    return prose, blocks


def declared_idea(text: str, task: str) -> str | None:
    """First algorithm name mentioned in the prose before the first code fence."""
    prose, _ = split_prose_code(text)
    lex = SORT_LEXICON if task == "T2" else PATH_LEXICON
    best: tuple[int, str] | None = None
    for label, pat in lex:
        m = re.search(pat, prose, flags=re.I)
        if m and (best is None or m.start() < best[0]):
            best = (m.start(), label)
    return None if best is None else best[1]


def _strip_docstrings(tree: ast.AST) -> ast.AST:
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(body, list):
            new_body = [
                s for s in body
                if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant)
                        and isinstance(s.value.value, str))
            ]
            if not new_body and body:
                new_body = [ast.Pass()]
            node.body = new_body  # type: ignore[attr-defined]
    return tree


def _parse_prefix(src: str) -> tuple[ast.Module | None, str]:
    """Parse src; on failure drop trailing lines until it parses ('partial')."""
    try:
        return ast.parse(src), "ok"
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        pass
    lines = src.splitlines()
    # dropping lines from the end; also try closing an open block with 'pass'
    for cut in range(len(lines) - 1, 0, -1):
        chunk = "\n".join(lines[:cut])
        for suffix in ("", "\n" + " " * 8 + "pass", "\n" + " " * 4 + "pass", "\n" + " " * 12 + "pass"):
            try:
                return ast.parse(chunk + suffix), "partial"
            except (SyntaxError, ValueError, RecursionError, MemoryError):
                continue
    return None, "unparseable"


def _looks_like_python(body: str) -> bool:
    return bool(re.search(r"^\s*(def |class |import |from |for |while |if |print\()", body, re.M))


def extract_code(text: str) -> dict:
    """Extract and clean the program from a model response.

    Returns {code (comment/docstring-stripped, unparsed), raw_code, parse_status,
    n_blocks, has_fence}.
    """
    _, blocks = split_prose_code(text)
    has_fence = bool(blocks)
    if blocks:
        py_blocks = [b for lang, b in blocks if lang in ("python", "py", "python3", "")]
        py_blocks = [b for b in py_blocks if _looks_like_python(b)] or py_blocks
    else:
        py_blocks = [text] if _looks_like_python(text) else []
    if not py_blocks:
        return {"code": "", "raw_code": "", "parse_status": "no_code", "n_blocks": 0, "has_fence": has_fence}
    def_blocks = [b for b in py_blocks if re.search(r"^\s*(def |class )", b, re.M)]
    use_blocks = def_blocks if def_blocks else py_blocks
    trees: list[ast.Module] = []
    status = "ok"
    joined = "\n\n".join(use_blocks)
    tree, st = _parse_prefix(joined)
    if tree is not None and st == "ok":
        trees = [tree]
    else:
        # parse blocks individually and keep what parses
        for b in use_blocks:
            t, s = _parse_prefix(b)
            if t is not None:
                trees.append(t)
                if s != "ok":
                    status = "partial"
        if not trees:
            return {"code": "", "raw_code": joined, "parse_status": "unparseable",
                    "n_blocks": len(use_blocks), "has_fence": has_fence}
        if len(trees) < len(use_blocks):
            status = "partial"
    body: list[ast.stmt] = []
    for t in trees:
        body.extend(t.body)
    mod = ast.Module(body=body, type_ignores=[])
    mod = _strip_docstrings(mod)
    try:
        code = ast.unparse(mod)
    except (ValueError, RecursionError, AttributeError, TypeError):
        return {"code": "", "raw_code": joined, "parse_status": "unparseable",
                "n_blocks": len(use_blocks), "has_fence": has_fence}
    return {"code": code, "raw_code": joined, "parse_status": status,
            "n_blocks": len(use_blocks), "has_fence": has_fence}


def lexical_proxy_char(text: str, task: str) -> int | None:
    """Char offset at which the first idea-identifying lexeme is COMPLETED.

    Matches an algorithm name anywhere (prose or code) or, for path tasks, a
    data-structure token (deque/heapq/stack/PriorityQueue). Used to place the
    lexical-proxy commitment position t_lex for probes.
    """
    lex = SORT_LEXICON if task == "T2" else PATH_LEXICON
    pats = [p for _, p in lex]
    if task != "T2":
        pats += [r"\bdeque\b", r"\bheapq\b", r"\bheappush\b", r"\bPriorityQueue\b", r"\bstack\b"]
    else:
        pats += [r"\bpivot\b", r"\bswapped\b", r"\bheapify\b", r"\bmin_idx\b", r"\bgap\b"]
    best = None
    for p in pats:
        m = re.search(p, text, flags=re.I)
        if m and (best is None or m.end() < best):
            best = m.end()
    return best
