from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import UUID
import re

from sqlalchemy.orm import Session

from app.core.config import settings
from app.repositories.artifacts import ArtifactRepository
from app.repositories.runs import RunRepository
from app.repositories.steps import StepRepository
from app.services.commands import CommandRunner
from app.services.fs import FileStore


@dataclass(frozen=True)
class EvalResult:
    ok: bool
    message: str


class RunSWEbenchEval:
    """Run a SWE-bench evaluation (predictions via Ollama → harness → report).

    This is intentionally *not* the normal patch workflow. It is a separate, real-world
    benchmark run that produces metrics under the run's artifact folder.
    """

    STEP_NAMES = [
        "Prepare evaluation",
        "Generate predictions",
        "Run SWE-bench harness",
        "Report",
    ]

    def __init__(self, db: Session, cfg: dict[str, str]) -> None:
        self._db = db
        self._cfg = cfg
        self._runs = RunRepository(db)
        self._steps = StepRepository(db)
        self._artifacts = ArtifactRepository(db)
        self._store = FileStore(settings.artifacts_dir)

    def start(self, run_id: UUID) -> EvalResult:
        run = self._runs.get(run_id)
        if not run:
            return EvalResult(ok=False, message="Run not found")

        existing = self._steps.list_for_run(run_id)
        if not existing:
            self._steps.init_steps(run_id, self.STEP_NAMES)

        started_at = datetime.utcnow()
        self._runs.set_status(run_id, "running")

        out_dir = self._store.run_dir(str(run_id))
        runner = CommandRunner(cwd=str(out_dir), timeout_seconds=max(300, settings.rq_job_timeout_seconds - 30))

        steps = self._steps.list_for_run(run_id)
        by_name = {s.name: s for s in steps}

        # Config
        prompt_dataset = self._cfg.get("prompt_dataset", self._cfg.get("dataset", settings.swebench_prompt_dataset))
        dataset_name = self._cfg.get("dataset_name", settings.swebench_dataset_name)
        split = self._cfg.get("split", "test")
        limit = int(self._cfg.get("limit", "0") or "0")
        max_workers = int(self._cfg.get("max_workers", str(settings.swebench_max_workers)) or str(settings.swebench_max_workers))

        ollama_url = self._cfg.get("ollama", os.getenv("OLLAMA_BASE_URL", settings.ollama_base_url))
        model = self._cfg.get("model", os.getenv("OLLAMA_MODEL", settings.ollama_model))
        temperature = float(self._cfg.get("temperature", os.getenv("OLLAMA_TEMPERATURE", str(settings.ollama_temperature))))
        num_ctx = int(self._cfg.get("num_ctx", os.getenv("OLLAMA_NUM_CTX", str(settings.ollama_num_ctx))))
        timeout_s = int(self._cfg.get("timeout", str(settings.ollama_timeout_seconds)) or str(settings.ollama_timeout_seconds))

        predictions_path = out_dir / "predictions.jsonl"

        # 1) Prepare
        s = by_name["Prepare evaluation"]
        self._steps.set_running(s.id)

        sock = Path("/var/run/docker.sock")
        if not sock.exists():
            msg = "Missing /var/run/docker.sock inside worker. SWE-bench harness needs Docker access."
            p = self._store.write_text(str(run_id), "eval_error.txt", msg)
            self._artifacts.add(run_id, "eval_error", p)
            self._steps.set_failed(s.id, error=msg, log_path=p)
            self._runs.set_status(run_id, "failed")
            return EvalResult(ok=False, message=msg)

        info = {
            "started_at": started_at.isoformat(),
            "prompt_dataset": prompt_dataset,
            "dataset_name": dataset_name,
            "split": split,
            "limit": limit,
            "max_workers": max_workers,
            "ollama": ollama_url,
            "model": model,
            "temperature": temperature,
            "num_ctx": num_ctx,
            "timeout_s": timeout_s,
        }
        cfg_path = self._store.write_json(str(run_id), "eval_config.json", info)
        self._artifacts.add(run_id, "eval_config", cfg_path)
        self._steps.set_success(s.id, summary="Config written", artifact_path=cfg_path)

        # 2) Generate predictions
        s = by_name["Generate predictions"]
        self._steps.set_running(s.id)

        gen_script = Path(settings.ml_dir) / "swebench" / "generate_predictions_ollama.py"
        if not gen_script.exists():
            msg = f"ML script not found: {gen_script}. Ensure ./ml is mounted to {settings.ml_dir}."
            p = self._store.write_text(str(run_id), "eval_error.txt", msg)
            self._artifacts.add(run_id, "eval_error", p)
            self._steps.set_failed(s.id, error=msg, log_path=p)
            self._runs.set_status(run_id, "failed")
            return EvalResult(ok=False, message=msg)

        cmd = [
            "python",
            str(gen_script),
            "--dataset",
            prompt_dataset,
            "--split",
            split,
            "--out",
            str(predictions_path),
            "--ollama",
            ollama_url,
            "--model",
            model,
            "--temperature",
            str(temperature),
            "--num_ctx",
            str(num_ctx),
            "--timeout",
            str(timeout_s),
        ]
        if limit:
            cmd.extend(["--limit", str(limit)])

        gen = runner.run(cmd)
        gen_log = (gen.stdout or "") + "\n" + (gen.stderr or "")
        gen_log_path = self._store.write_text(str(run_id), "predictions_generate.log", gen_log)
        self._artifacts.add(run_id, "predictions_generate_log", gen_log_path)

        if gen.code != 0 or not predictions_path.exists():
            msg = "Failed to generate predictions (see predictions_generate.log)"
            # Try to capture root cause in a compact artifact.
            detail = self._extract_error_excerpt(gen_log)
            if detail:
                err_path = self._store.write_text(str(run_id), "eval_error.txt", detail)
                self._artifacts.add(run_id, "eval_error", err_path)
                msg = f"{msg} | {detail.splitlines()[0]}"
            self._steps.set_failed(s.id, error=msg, log_path=gen_log_path)
            self._runs.set_status(run_id, "failed")
            return EvalResult(ok=False, message=msg)

        self._artifacts.add(run_id, "predictions", str(predictions_path))
        self._steps.set_success(s.id, summary=f"Wrote predictions.jsonl", log_path=gen_log_path, artifact_path=str(predictions_path))

        # 3) Run harness
        s = by_name["Run SWE-bench harness"]
        self._steps.set_running(s.id)

        harness_cmd = [
            "python",
            "-m",
            "swebench.harness.run_evaluation",
            "--dataset_name",
            dataset_name,
            "--predictions_path",
            str(predictions_path),
            "--max_workers",
            str(max_workers),
            "--run_id",
            str(run_id),
        ]

        harness = runner.run(harness_cmd)
        harness_log = (harness.stdout or "") + "\n" + (harness.stderr or "")
        harness_log_path = self._store.write_text(str(run_id), "harness.log", harness_log)
        self._artifacts.add(run_id, "harness_log", harness_log_path)

        results_json = out_dir / "evaluation_results" / str(run_id) / "results.json"
        if harness.code != 0 or not results_json.exists():
            msg = "Harness failed or results.json missing (see harness.log)"
            detail = self._extract_error_excerpt(harness_log)
            if detail:
                err_path = self._store.write_text(str(run_id), "eval_error.txt", detail)
                self._artifacts.add(run_id, "eval_error", err_path)
                msg = f"{msg} | {detail.splitlines()[0]}"
            self._steps.set_failed(s.id, error=msg, log_path=harness_log_path)
            self._runs.set_status(run_id, "failed")
            return EvalResult(ok=False, message=msg)

        self._artifacts.add(run_id, "swebench_results_json", str(results_json))
        self._steps.set_success(s.id, summary="Harness completed", log_path=harness_log_path, artifact_path=str(results_json))

        # 4) Report
        s = by_name["Report"]
        self._steps.set_running(s.id)

        summarize_script = Path(settings.ml_dir) / "swebench" / "summarize_results.py"
        report_path = out_dir / "report.md"
        sum_cmd = [
            "python",
            str(summarize_script),
            "--run_id",
            str(run_id),
            "--results_dir",
            "evaluation_results",
            "--out",
            str(report_path),
        ]
        rep = runner.run(sum_cmd)
        rep_log = (rep.stdout or "") + "\n" + (rep.stderr or "")
        rep_log_path = self._store.write_text(str(run_id), "report_build.log", rep_log)
        self._artifacts.add(run_id, "report_build_log", rep_log_path)

        if rep.code != 0 or not report_path.exists():
            msg = "Report generation failed (see report_build.log)"
            self._steps.set_failed(s.id, error=msg, log_path=rep_log_path)
            self._runs.set_status(run_id, "failed")
            return EvalResult(ok=False, message=msg)

        self._artifacts.add(run_id, "report", str(report_path))

        # Also write a compact metrics.json for quick programmatic checks
        try:
            data = json.loads(results_json.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        metrics_path = self._store.write_json(str(run_id), "metrics.json", {"results": data})
        self._artifacts.add(run_id, "metrics", metrics_path)

        self._steps.set_success(s.id, summary="Report ready", artifact_path=str(report_path), log_path=rep_log_path)

        self._runs.set_status(run_id, "completed")
        return EvalResult(ok=True, message="Completed")

    @staticmethod
    def _extract_error_excerpt(log_text: str, max_lines: int = 20) -> str | None:
        """Extract a short root-cause excerpt from long logs."""
        if not log_text:
            return None
        lines = (log_text or "").splitlines()

        # Prefer traceback tail if present.
        tb_start = None
        for i, ln in enumerate(lines):
            if "Traceback (most recent call last):" in ln:
                tb_start = i
        if tb_start is not None:
            excerpt = lines[tb_start: tb_start + max_lines]
            return "Root cause (traceback excerpt):\n" + "\n".join(excerpt)

        # Otherwise try common failure signatures.
        patterns = [
            r"ReadTimeout",
            r"ConnectTimeout",
            r"Patch Apply Failed",
            r"malformed patch",
            r"No file to patch",
            r"error=\d+",
        ]
        hits: list[str] = []
        for ln in lines:
            if any(re.search(p, ln, flags=re.IGNORECASE) for p in patterns):
                hits.append(ln)
                if len(hits) >= max_lines:
                    break
        if hits:
            return "Root cause (log excerpt):\n" + "\n".join(hits)

        return None
