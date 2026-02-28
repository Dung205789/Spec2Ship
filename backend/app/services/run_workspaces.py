from __future__ import annotations

import shutil
from pathlib import Path

from app.core.config import settings


def _ignore_patterns():
    # Avoid huge, noisy folders in copies.
    return shutil.ignore_patterns(
        ".git",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".venv",
        "venv",
        "node_modules",
        "dist",
        "build",
        ".next",
        ".spec2ship_patch.diff",
        ".spec2ship_check.diff",
    )


def ensure_run_workspace(run_id: str, base_workspace_path: str) -> str:
    """Return the workspace path the pipeline should operate on.

    If isolate_workspaces is enabled, we create a per-run sandbox:
      /data/run_workspaces/<run_id>

    This prevents cross-run contamination and makes retries deterministic.
    """
    if not getattr(settings, "isolate_workspaces", False):
        return base_workspace_path

    dst = Path(settings.run_workspaces_dir) / str(run_id)
    if dst.exists():
        return str(dst)

    dst.parent.mkdir(parents=True, exist_ok=True)

    src = Path(base_workspace_path)
    if not src.exists():
        raise RuntimeError(f"Workspace not found: {src}")

    shutil.copytree(src, dst, dirs_exist_ok=True, ignore=_ignore_patterns())
    return str(dst)


def reset_run_workspace(run_id: str, base_workspace_path: str) -> str:
    """Delete and recreate the per-run workspace sandbox."""
    if not getattr(settings, "isolate_workspaces", False):
        return base_workspace_path

    dst = Path(settings.run_workspaces_dir) / str(run_id)
    if dst.exists():
        shutil.rmtree(dst, ignore_errors=True)
    return ensure_run_workspace(run_id, base_workspace_path)


def cleanup_run_workspace(run_id: str) -> None:
    if not getattr(settings, "isolate_workspaces", False):
        return
    dst = Path(settings.run_workspaces_dir) / str(run_id)
    if dst.exists():
        shutil.rmtree(dst, ignore_errors=True)
