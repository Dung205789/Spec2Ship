from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import time
from typing import Iterable
from zipfile import ZipFile


@dataclass(frozen=True)
class WorkspaceInfo:
    name: str
    path: str
    exists: bool


@dataclass(frozen=True)
class WorkspaceImportResult:
    name: str
    path: str
    file_count: int
    extracted_bytes: int
    skipped_files: int
    note: str | None = None


def resolve_workspace_path(default_path: str, workspace_name: str, workspaces_root: str = "/workspace/workspaces") -> str:
    """Resolve a workspace name to an on-disk path.

    Safety: only allow simple names and keep everything under /workspace.
    """
    name = (workspace_name or "").strip()
    if not name:
        return default_path

    # Allow the default name.
    if name == "sample_workspace":
        return default_path

    # Only allow simple folder names (no slashes, no traversal).
    if "/" in name or "\\" in name or ".." in name:
        return default_path

    candidate = Path(workspaces_root) / name
    return str(candidate) if candidate.exists() else default_path


def list_workspaces(default_path: str, workspaces_root: str = "/workspace/workspaces") -> list[WorkspaceInfo]:
    root = Path(workspaces_root)
    root.mkdir(parents=True, exist_ok=True)

    out: list[WorkspaceInfo] = []
    # Sample workspace is always available.
    out.append(WorkspaceInfo(name="sample_workspace", path=default_path, exists=Path(default_path).exists()))

    for p in sorted(root.iterdir() if root.exists() else [], key=lambda x: x.name.lower()):
        if not p.is_dir():
            continue
        # Only expose simple names.
        if "/" in p.name or "\\" in p.name or ".." in p.name:
            continue
        out.append(WorkspaceInfo(name=p.name, path=str(p), exists=True))
    return out


_SAFE_NAME_RE = re.compile(r"[^a-zA-Z0-9._-]+");


def sanitize_workspace_name(name: str) -> str:
    n = (name or "").strip()
    if not n:
        return "workspace"
    n = _SAFE_NAME_RE.sub("-", n)
    n = n.strip("-._")
    if not n:
        n = "workspace"
    return n[:64]


def _should_skip_entry(rel_posix: str) -> bool:
    # Skip huge/noisy folders by default.
    # (Customers should upload source-only; deps are installed by pipeline commands.)
    parts = rel_posix.split("/")
    if not parts:
        return False
    top = parts[0]
    if top in {".git", "node_modules", "dist", "build", ".next", ".venv", "venv", "__pycache__"}:
        return True
    return False


def _iter_zip_files(z: ZipFile) -> Iterable:
    for info in z.infolist():
        # Directories are signaled by trailing slash.
        if info.filename.endswith("/"):
            continue
        yield info


def import_workspace_zip(
    zip_path: str,
    requested_name: str | None,
    workspaces_root: str,
    *,
    max_files: int,
    max_total_bytes: int,
    max_file_bytes: int,
) -> WorkspaceImportResult:
    """Import a ZIP archive into a new workspace folder.

    Safety:
    - Prevent path traversal (.., absolute paths, drive letters)
    - Enforce size limits (zip bombs)
    - Skip known huge folders (node_modules/.git/etc)
    """

    root = Path(workspaces_root)
    root.mkdir(parents=True, exist_ok=True)

    base = sanitize_workspace_name(requested_name or Path(zip_path).stem)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    # add short monotonic-ish suffix to avoid collisions
    suffix = f"{int(time.time() * 1000) % 100000:05d}"
    name = f"{base}-{stamp}-{suffix}"

    dest = root / name
    dest.mkdir(parents=True, exist_ok=False)

    extracted_bytes = 0
    file_count = 0
    skipped = 0

    dest_resolved = dest.resolve()

    with ZipFile(zip_path) as z:
        infos = list(_iter_zip_files(z))
        if len(infos) > max_files:
            raise RuntimeError(f"ZIP contains too many files: {len(infos)} > {max_files}")

        for info in infos:
            # zipfile uses forward slashes even on Windows
            rel = info.filename.replace("\\", "/").lstrip("/")

            # Reject drive letters / absolute paths / traversal
            if re.match(r"^[a-zA-Z]:/", rel):
                skipped += 1
                continue
            if ".." in rel.split("/"):
                skipped += 1
                continue

            if _should_skip_entry(rel):
                skipped += 1
                continue

            if info.file_size > max_file_bytes:
                skipped += 1
                continue

            # Enforce total extraction size
            if extracted_bytes + info.file_size > max_total_bytes:
                raise RuntimeError(
                    f"ZIP extraction would exceed limit: {extracted_bytes + info.file_size} > {max_total_bytes}"
                )

            out_path = (dest / rel).resolve()
            # Ensure output stays within dest
            if not str(out_path).startswith(str(dest_resolved)):
                skipped += 1
                continue

            out_path.parent.mkdir(parents=True, exist_ok=True)
            with z.open(info) as src, open(out_path, "wb") as dst:
                dst.write(src.read())

            extracted_bytes += info.file_size
            file_count += 1

    # Write a small manifest for traceability
    meta = dest / ".spec2ship_workspace.json"
    meta.write_text(
        (
            "{\n"
            f"  \"name\": \"{name}\",\n"
            f"  \"created_at\": \"{time.strftime('%Y-%m-%dT%H:%M:%S')}\",\n"
            f"  \"file_count\": {file_count},\n"
            f"  \"extracted_bytes\": {extracted_bytes},\n"
            f"  \"skipped_files\": {skipped}\n"
            "}\n"
        ),
        encoding="utf-8",
    )

    note = None
    if skipped:
        note = "Some files were skipped (e.g., node_modules/.git or unsafe paths)"

    return WorkspaceImportResult(
        name=name,
        path=str(dest),
        file_count=file_count,
        extracted_bytes=extracted_bytes,
        skipped_files=skipped,
        note=note,
    )


BUGGY_PRICING = """\
\"\"\"Pricing rules for tinyshop.

apply_discount() currently rounds down instead of half-up.
The test suite captures the expected behaviour.
\"\"\"


def apply_discount(total_cents: int, percent: int) -> int:
    \"\"\"Return discounted total in cents.

    Rules:
    - percent is an integer 0..100
    - rounding is **half-up** to the nearest cent

    Current implementation is wrong (rounds down).
    \"\"\"
    percent = max(0, min(100, percent))

    # BUG: int() floors, so 895.5 becomes 895 (should be 896)
    return int(total_cents * (100 - percent) / 100)
"""


MAIN_WITHOUT_HEALTH = """\
from fastapi import FastAPI
from pydantic import BaseModel

from tinyshop.pricing import apply_discount

app = FastAPI(title=\"tinyshop\")


class DiscountIn(BaseModel):
    total_cents: int
    percent: int


@app.post(\"/discount\")
def discount(payload: DiscountIn) -> dict:
    return {\"discounted_cents\": apply_discount(payload.total_cents, payload.percent)}
"""


def reset_sample_workspace(workspace_path: str) -> None:
    """Reset the sample workspace back to the known-broken starting point."""
    root = Path(workspace_path)
    pricing = root / "tinyshop" / "pricing.py"
    pricing.parent.mkdir(parents=True, exist_ok=True)
    pricing.write_text(BUGGY_PRICING, encoding="utf-8")

    main = root / "tinyshop" / "main.py"
    main.parent.mkdir(parents=True, exist_ok=True)
    main.write_text(MAIN_WITHOUT_HEALTH, encoding="utf-8")
