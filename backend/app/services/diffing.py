from __future__ import annotations

import difflib
from pathlib import Path
from typing import Iterable


def snapshot_files(root: str, include_globs: list[str]) -> dict[str, str]:
    base = Path(root)
    out: dict[str, str] = {}
    for g in include_globs:
        for p in base.rglob(g):
            if p.is_file():
                rel = str(p.relative_to(base))
                out[rel] = p.read_text(encoding="utf-8")
    return out


def unified_diff(before: dict[str, str], after: dict[str, str]) -> str:
    paths = sorted(set(before.keys()) | set(after.keys()))
    chunks: list[str] = []
    for path in paths:
        a = before.get(path, "").splitlines(keepends=True)
        b = after.get(path, "").splitlines(keepends=True)
        if a == b:
            continue
        # Add diff --git header so git apply works reliably in all modes
        chunks.append(f"diff --git a/{path} b/{path}\n")
        chunks.extend(
            difflib.unified_diff(
                a,
                b,
                fromfile=f"a/{path}",
                tofile=f"b/{path}",
            )
        )
    return "".join(chunks) if chunks else "(no changes)"
