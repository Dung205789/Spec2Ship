from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import settings
from app.repositories.artifacts import ArtifactRepository
from app.repositories.runs import RunRepository
from app.repositories.steps import StepRepository
from app.services.commands import CommandRunner
from app.services.fs import FileStore


@dataclass(frozen=True)
class TrainEvalResult:
    ok: bool
    message: str


class RunSWEbenchTrainLoRA:
    """Train a LoRA adapter on a real SWE-bench-style dataset, then evaluate on SWE-bench harness.

    Steps:
      1) Prepare (write config + verify docker sock for harness)
      2) Train LoRA adapter (HF + PEFT)
      3) Generate predictions (HF inference using base model + adapter)
      4) Run SWE-bench harness
      5) Report (report.md + metrics.json)
    """

    STEP_NAMES = [
        "Prepare training",
        "Train LoRA",
        "Generate predictions (HF)",
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

    def start(self, run_id: UUID) -> TrainEvalResult:
        run = self._runs.get(run_id)
        if not run:
            return TrainEvalResult(ok=False, message="Run not found")

        existing = self._steps.list_for_run(run_id)
        if not existing:
            self._steps.init_steps(run_id, self.STEP_NAMES)

        started_at = datetime.utcnow()
        self._runs.set_status(run_id, "running")

        out_dir = self._store.run_dir(str(run_id))
        runner = CommandRunner(
            cwd=str(out_dir),
            timeout_seconds=max(300, settings.rq_job_timeout_seconds - 30),
        )

        steps = self._steps.list_for_run(run_id)
        by_name = {s.name: s for s in steps}

        # ---- Config (training) ----
        base_model = self._cfg.get("base_model", os.getenv("HF_MODEL", getattr(settings, "hf_model", "")) or "Qwen/Qwen2.5-Coder-0.5B-Instruct")
        train_dataset = self._cfg.get("train_dataset", "princeton-nlp/SWE-bench_bm25_13K")
        train_split = self._cfg.get("train_split", self._cfg.get("train_split", "train"))
        train_limit = int(self._cfg.get("train_limit", "200") or "200")
        max_steps = int(self._cfg.get("max_steps", "100") or "100")
        learning_rate = float(self._cfg.get("learning_rate", "2e-4") or "2e-4")
        batch_size = int(self._cfg.get("batch_size", "1") or "1")
        grad_accum = int(self._cfg.get("grad_accum", "8") or "8")
        max_seq_len = int(self._cfg.get("max_seq_len", "2048") or "2048")
        device = self._cfg.get("device", os.getenv("HF_DEVICE", "cpu"))

        # ---- Config (evaluation) ----
        prompt_dataset = self._cfg.get("prompt_dataset", self._cfg.get("dataset", settings.swebench_prompt_dataset))
        dataset_name = self._cfg.get("dataset_name", settings.swebench_dataset_name)
        split = self._cfg.get("split", "test")
        limit = int(self._cfg.get("limit", "0") or "0")
        max_workers = int(self._cfg.get("max_workers", str(settings.swebench_max_workers)) or str(settings.swebench_max_workers))

        max_new_tokens = int(self._cfg.get("max_new_tokens", "512") or "512")
        temperature = float(self._cfg.get("temperature", "0.2") or "0.2")
        top_p = float(self._cfg.get("top_p", "0.95") or "0.95")

        adapter_dir = out_dir / "lora_adapter"
        predictions_path = out_dir / "predictions.hf.jsonl"

        # 1) Prepare
        s = by_name["Prepare training"]
        self._steps.set_running(s.id)

        sock = Path("/var/run/docker.sock")
        if not sock.exists():
            msg = "Missing /var/run/docker.sock inside worker. SWE-bench harness needs Docker access."
            p = self._store.write_text(str(run_id), "train_eval_error.txt", msg)
            self._artifacts.add(run_id, "train_eval_error", p)
            self._steps.set_failed(s.id, error=msg, log_path=p)
            self._runs.set_status(run_id, "failed")
            return TrainEvalResult(ok=False, message=msg)

        info = {
            "started_at": started_at.isoformat(),
            "base_model": base_model,
            "train_dataset": train_dataset,
            "train_split": train_split,
            "train_limit": train_limit,
            "max_steps": max_steps,
            "learning_rate": learning_rate,
            "batch_size": batch_size,
            "grad_accum": grad_accum,
            "max_seq_len": max_seq_len,
            "device": device,
            "prompt_dataset": prompt_dataset,
            "dataset_name": dataset_name,
            "split": split,
            "limit": limit,
            "max_workers": max_workers,
            "max_new_tokens": max_new_tokens,
            "temperature": temperature,
            "top_p": top_p,
        }
        cfg_path = self._store.write_json(str(run_id), "train_eval_config.json", info)
        self._artifacts.add(run_id, "train_eval_config", cfg_path)
        self._steps.set_success(s.id, summary="Config written", artifact_path=cfg_path)

        # 2) Train LoRA
        s = by_name["Train LoRA"]
        self._steps.set_running(s.id)

        train_script = Path(settings.ml_dir) / "training" / "train_lora_swebench.py"
        if not train_script.exists():
            msg = f"Training script not found: {train_script}. Ensure ./ml is mounted to {settings.ml_dir}."
            p = self._store.write_text(str(run_id), "train_error.txt", msg)
            self._artifacts.add(run_id, "train_error", p)
            self._steps.set_failed(s.id, error=msg, log_path=p)
            self._runs.set_status(run_id, "failed")
            return TrainEvalResult(ok=False, message=msg)

        train_cmd = [
            "python",
            str(train_script),
            "--base_model",
            base_model,
            "--dataset",
            train_dataset,
            "--split",
            train_split,
            "--output_dir",
            str(adapter_dir),
            "--max_steps",
            str(max_steps),
            "--learning_rate",
            str(learning_rate),
            "--batch_size",
            str(batch_size),
            "--grad_accum",
            str(grad_accum),
            "--max_seq_len",
            str(max_seq_len),
            "--device",
            device,
        ]
        if train_limit:
            train_cmd.extend(["--limit", str(train_limit)])

        tr = runner.run(train_cmd)
        tr_log = (tr.stdout or "") + "\n" + (tr.stderr or "")
        tr_log_path = self._store.write_text(str(run_id), "train_lora.log", tr_log)
        self._artifacts.add(run_id, "train_lora_log", tr_log_path)

        if tr.code != 0 or not adapter_dir.exists():
            msg = "LoRA training failed (see train_lora.log)"
            self._steps.set_failed(s.id, error=msg, log_path=tr_log_path)
            self._runs.set_status(run_id, "failed")
            return TrainEvalResult(ok=False, message=msg)

        self._artifacts.add(run_id, "lora_adapter_dir", str(adapter_dir))
        meta_path = adapter_dir / "train_meta.json"
        if meta_path.exists():
            self._artifacts.add(run_id, "lora_train_meta", str(meta_path))
        self._steps.set_success(s.id, summary="Adapter trained", log_path=tr_log_path, artifact_path=str(adapter_dir))

        # 3) Generate predictions (HF)
        s = by_name["Generate predictions (HF)"]
        self._steps.set_running(s.id)

        gen_script = Path(settings.ml_dir) / "swebench" / "generate_predictions_hf.py"
        if not gen_script.exists():
            msg = f"HF generation script not found: {gen_script}. Ensure ./ml is mounted to {settings.ml_dir}."
            p = self._store.write_text(str(run_id), "predictions_error.txt", msg)
            self._artifacts.add(run_id, "predictions_error", p)
            self._steps.set_failed(s.id, error=msg, log_path=p)
            self._runs.set_status(run_id, "failed")
            return TrainEvalResult(ok=False, message=msg)

        gen_cmd = [
            "python",
            str(gen_script),
            "--dataset",
            prompt_dataset,
            "--split",
            split,
            "--out",
            str(predictions_path),
            "--base_model",
            base_model,
            "--adapter",
            str(adapter_dir),
            "--max_new_tokens",
            str(max_new_tokens),
            "--temperature",
            str(temperature),
            "--top_p",
            str(top_p),
            "--device",
            device,
        ]
        if limit:
            gen_cmd.extend(["--limit", str(limit)])

        gen = runner.run(gen_cmd)
        gen_log = (gen.stdout or "") + "\n" + (gen.stderr or "")
        gen_log_path = self._store.write_text(str(run_id), "predictions_hf_generate.log", gen_log)
        self._artifacts.add(run_id, "predictions_hf_generate_log", gen_log_path)

        if gen.code != 0 or not predictions_path.exists():
            msg = "Failed to generate HF predictions (see predictions_hf_generate.log)"
            self._steps.set_failed(s.id, error=msg, log_path=gen_log_path)
            self._runs.set_status(run_id, "failed")
            return TrainEvalResult(ok=False, message=msg)

        self._artifacts.add(run_id, "predictions_hf", str(predictions_path))
        self._steps.set_success(s.id, summary="Wrote predictions.hf.jsonl", log_path=gen_log_path, artifact_path=str(predictions_path))

        # 4) Run harness
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
        harness_log_path = self._store.write_text(str(run_id), "harness_hf.log", harness_log)
        self._artifacts.add(run_id, "harness_hf_log", harness_log_path)

        results_json = out_dir / "evaluation_results" / str(run_id) / "results.json"
        if harness.code != 0 or not results_json.exists():
            msg = "Harness failed or results.json missing (see harness_hf.log)"
            self._steps.set_failed(s.id, error=msg, log_path=harness_log_path)
            self._runs.set_status(run_id, "failed")
            return TrainEvalResult(ok=False, message=msg)

        self._artifacts.add(run_id, "swebench_results_json", str(results_json))
        self._steps.set_success(s.id, summary="Harness completed", log_path=harness_log_path, artifact_path=str(results_json))

        # 5) Report
        s = by_name["Report"]
        self._steps.set_running(s.id)

        summarize_script = Path(settings.ml_dir) / "swebench" / "summarize_results.py"
        report_path = out_dir / "report_hf.md"
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
        rep_log_path = self._store.write_text(str(run_id), "report_hf_build.log", rep_log)
        self._artifacts.add(run_id, "report_hf_build_log", rep_log_path)

        if rep.code != 0 or not report_path.exists():
            msg = "Report generation failed (see report_hf_build.log)"
            self._steps.set_failed(s.id, error=msg, log_path=rep_log_path)
            self._runs.set_status(run_id, "failed")
            return TrainEvalResult(ok=False, message=msg)

        self._artifacts.add(run_id, "report_hf", str(report_path))

        # compact metrics
        try:
            data = json.loads(results_json.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        metrics_path = self._store.write_json(str(run_id), "metrics_hf.json", {"results": data})
        self._artifacts.add(run_id, "metrics_hf", metrics_path)

        self._steps.set_success(s.id, summary="Report ready", artifact_path=str(report_path), log_path=rep_log_path)
        self._runs.set_status(run_id, "completed")
        return TrainEvalResult(ok=True, message="Completed")
