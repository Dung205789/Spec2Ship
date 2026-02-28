from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.config import settings


def overrides_path_for_run(run_id: str) -> Path:
    return Path(settings.artifacts_dir) / str(run_id) / "run_overrides.json"


def load_run_overrides(run_id: str) -> dict[str, Any]:
    p = overrides_path_for_run(run_id)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_run_overrides(run_id: str, overrides: dict[str, Any]) -> None:
    p = overrides_path_for_run(run_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(overrides, ensure_ascii=False, indent=2), encoding="utf-8")
