from __future__ import annotations

import json
from pathlib import Path


class FileStore:
    def __init__(self, base_dir: str) -> None:
        self._base = Path(base_dir)
        self._base.mkdir(parents=True, exist_ok=True)

    def run_dir(self, run_id: str) -> Path:
        d = self._base / run_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def write_text(self, run_id: str, name: str, content: str) -> str:
        path = self.run_dir(run_id) / name
        path.write_text(content, encoding="utf-8")
        return str(path)

    def write_json(self, run_id: str, name: str, obj) -> str:
        path = self.run_dir(run_id) / name
        path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(path)

    def read_text(self, path: str) -> str:
        return Path(path).read_text(encoding="utf-8")

    def exists(self, path: str) -> bool:
        return Path(path).exists()
