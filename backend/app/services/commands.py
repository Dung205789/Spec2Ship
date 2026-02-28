from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CommandResult:
    code: int
    stdout: str
    stderr: str


class CommandRunner:
    def __init__(self, cwd: str, timeout_seconds: int = 90) -> None:
        self._cwd = Path(cwd)
        self._timeout = timeout_seconds

    def run(self, cmd: list[str], timeout_seconds: int | None = None) -> CommandResult:
        to = self._timeout if timeout_seconds is None else timeout_seconds
        try:
            completed = subprocess.run(
                cmd,
                cwd=self._cwd,
                capture_output=True,
                text=True,
                timeout=to,
            )
            return CommandResult(code=completed.returncode, stdout=completed.stdout, stderr=completed.stderr)
        except subprocess.TimeoutExpired as e:
            out = (e.stdout or "") if isinstance(e.stdout, str) else (e.stdout.decode(errors="ignore") if e.stdout else "")
            err = (e.stderr or "") if isinstance(e.stderr, str) else (e.stderr.decode(errors="ignore") if e.stderr else "")
            err = err + f"\n[timeout] command exceeded {to}s" 
            return CommandResult(code=124, stdout=out, stderr=err)
