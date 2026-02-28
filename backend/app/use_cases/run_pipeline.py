from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import settings
from app.repositories.artifacts import ArtifactRepository
from app.repositories.runs import RunRepository
from app.repositories.steps import StepRepository
from app.services.bug_detector import BugDetector
from app.services.commands import CommandRunner
from app.services.directives import parse_spec2ship_directives
from app.services.fs import FileStore
from app.services.kb import KnowledgeBase
from app.services.code_context import build_code_context
from app.services.patches import OllamaWorkspacePatcher, PatchProposal, WorkspacePatcher
from app.services.run_overrides import load_run_overrides
from app.services.run_workspaces import ensure_run_workspace
from app.services.workspace_profile import load_workspace_profile
from app.services.workspaces import resolve_workspace_path


@dataclass(frozen=True)
class UseCaseResult:
    ok: bool
    message: str


STEP_NAMES: list[str] = [
    "Preflight",
    "Baseline checks",
    "Summarize issues",
    "Context search",
    "Plan",
    "Propose patch",
    "Waiting for approval",
    "Apply patch",
    "Re-run checks",
    "Smoke test",
    "Report",
]


class RunPipeline:
    def __init__(self, db: Session) -> None:
        self._db = db
        self._runs = RunRepository(db)
        self._steps = StepRepository(db)
        self._artifacts = ArtifactRepository(db)
        self._store = FileStore(settings.artifacts_dir)

    def start(self, run_id: UUID) -> UseCaseResult:
        run = self._runs.get(run_id)
        if not run:
            return UseCaseResult(ok=False, message="Run not found")

        existing = self._steps.list_for_run(run_id)
        if not existing or len(existing) != len(STEP_NAMES) or [s.name for s in existing] != STEP_NAMES:
            if existing:
                self._steps.delete_for_run(run_id)
            self._steps.init_steps(run_id, STEP_NAMES)
            existing = self._steps.list_for_run(run_id)

        steps_by_name = {s.name: s for s in existing}
        self._runs.set_status(run_id, "running")

        base_ws = resolve_workspace_path(settings.workspace_path, run.workspace, settings.workspaces_root)
        ws = ensure_run_workspace(str(run_id), base_ws)

        profile = load_workspace_profile(ws)
        runner = CommandRunner(cwd=ws, timeout_seconds=settings.max_command_seconds)
        bug_detector = BugDetector()

        mode, cfg = parse_spec2ship_directives(run.ticket_text)
        overrides = load_run_overrides(str(run_id))
        effective_patcher = (
            (overrides.get("patcher_mode") or cfg.get("patcher") or cfg.get("patcher_mode") or settings.patcher_mode)
            .strip()
            .lower()
        )
        if effective_patcher not in {"rules", "ollama", "hf"}:
            effective_patcher = "rules"

        def run_shell(cmd: str, *, timeout: int) -> tuple[int, str, str]:
            res = runner.run(["bash", "-lc", cmd], timeout_seconds=timeout)
            return res.code, res.stdout, res.stderr

        def ensure_not_canceled() -> None:
            self._db.expire_all()
            r = self._runs.get(run_id)
            if r and r.status == "canceled":
                raise RuntimeError("Run canceled by user")

        def write_artifact(kind: str, name: str, content: str) -> str:
            p = self._store.write_text(str(run_id), name, content)
            self._artifacts.add(run_id, kind=kind, path=p)
            return p

        def read_text_safe(p: str) -> str:
            try:
                return Path(p).read_text(encoding="utf-8", errors="replace")
            except Exception:
                return ""

        def latest_test_output() -> tuple[str, str]:
            cand = [
                self._store.run_dir(str(run_id)) / "post_checks.log",
                self._store.run_dir(str(run_id)) / "baseline.log",
            ]
            for p in cand:
                if p.exists():
                    text = p.read_text(encoding="utf-8", errors="replace")
                    if text.strip():
                        return text, ""
            return "", ""

        # ---- Step 1: Preflight ----
        s = steps_by_name["Preflight"]
        if s.status in {"pending", "failed"}:
            self._steps.set_running(s.id)
            ensure_not_canceled()

            # Auto-detected profile: note it in the preflight log
            profile_note = ""
            if getattr(profile, "auto_detected", False):
                profile_note = f"\n[INFO] Auto-detected project type: {profile.name}\nBaseline command: {profile.baseline}\n"

            cmd = profile.preflight or "echo preflight_ok"
            code, out, err = run_shell(cmd, timeout=getattr(settings, "preflight_seconds", 30))
            log_content = f"$ {cmd}\n\n{out}\n{err}{profile_note}"
            log_path = write_artifact("preflight_log", "preflight.log", log_content)

            if code != 0:
                self._steps.set_failed(s.id, error="Preflight failed (workspace/environment).", log_path=log_path)
                self._runs.set_status(run_id, "failed")
                return UseCaseResult(ok=False, message="Preflight failed")
            summary = f"OK — profile: {profile.name}" + (" (auto-detected)" if getattr(profile, "auto_detected", False) else "")
            self._steps.set_success(s.id, summary=summary, log_path=log_path)

        # ---- Step 2: Baseline checks ----
        s = steps_by_name["Baseline checks"]
        if s.status in {"pending", "failed"}:
            self._steps.set_running(s.id)
            ensure_not_canceled()
            cmd = profile.baseline
            code, out, err = run_shell(cmd, timeout=settings.test_command_seconds)
            log_path = write_artifact("baseline_log", "baseline.log", f"$ {cmd}\n\n{out}\n{err}")

            fatal = (code == 127) or ("command not found" in (err or "").lower())
            if fatal:
                self._steps.set_failed(
                    s.id,
                    error="Baseline command failed to run (environment/config). Check preflight log.",
                    log_path=log_path,
                )
                self._runs.set_status(run_id, "failed")
                return UseCaseResult(ok=False, message="Baseline command failed")

            if code == 0:
                self._steps.set_success(s.id, summary="OK (no failures detected)", log_path=log_path)
            else:
                self._steps.set_success(s.id, summary=f"Found failures (exit {code})", log_path=log_path)

        # ---- Step 3: Summarize issues ----
        s = steps_by_name["Summarize issues"]
        signals_text = ""
        if s.status in {"pending", "failed"}:
            self._steps.set_running(s.id)
            ensure_not_canceled()
            out, err = latest_test_output()
            signals = bug_detector.from_output(out, err, language=getattr(profile, "language", None))
            payload = {
                "signals": [sig.__dict__ for sig in signals],
                "workspace_profile": {
                    "name": profile.name,
                    "language": profile.language,
                    "baseline": profile.baseline,
                    "auto_detected": getattr(profile, "auto_detected", False),
                },
            }
            json_path = self._store.write_json(str(run_id), "signals.json", payload)
            self._artifacts.add(run_id, kind="signals_json", path=json_path)
            signals_text = "\n".join([f"- [{sig.kind}] {sig.summary}: {sig.details}" for sig in signals]) or "(no signals parsed from output)"
            txt_path = write_artifact("signals_text", "signals.txt", signals_text)
            self._steps.set_success(s.id, summary=f"{len(signals)} signal(s) extracted", artifact_path=txt_path)
        else:
            if s.artifact_path and Path(s.artifact_path).exists():
                signals_text = read_text_safe(s.artifact_path)
            else:
                signals_text = "(no signals)"

        # ---- Step 4: Context search ----
        s = steps_by_name["Context search"]
        ctx_text = ""
        if s.status in {"pending", "failed"}:
            self._steps.set_running(s.id)
            ensure_not_canceled()

            kb_path = self._store.run_dir(str(run_id)).parent / "kb.json"
            kb = KnowledgeBase(str(kb_path))
            kb.load()
            docs_folder = f"{ws}/docs"
            try:
                ingested = kb.ingest_folder(docs_folder, glob="*.md")
            except Exception:
                ingested = 0

            ctx = kb.search(run.ticket_text, k=4)
            kb_text = "\n\n".join([f"### {d.title}\n{d.text[:1200]}" for d in ctx]) if ctx else "(no matching docs)"

            # Enhanced code context
            code_ctx = build_code_context(
                workspace_path=ws,
                ticket_text=run.ticket_text,
                signals_text=signals_text,
                max_files=settings.code_context_max_files,
                max_chars=settings.code_context_max_chars,
            )

            ctx_text = (
                "## KB docs (from workspace /docs)\n"
                + kb_text
                + "\n\n## Code context (most relevant files)\n"
                + code_ctx
            )
            path = write_artifact("context", "context.md", ctx_text)
            kb_note = f"{ingested} doc(s) indexed" if ingested > 0 else "no docs folder"
            self._steps.set_success(s.id, summary=f"Context built — {kb_note}", artifact_path=path)
        else:
            if s.artifact_path and Path(s.artifact_path).exists():
                ctx_text = read_text_safe(s.artifact_path)

        # ---- Step 5: Plan ----
        s = steps_by_name["Plan"]
        plan_text = ""
        if s.status in {"pending", "failed"}:
            self._steps.set_running(s.id)
            ensure_not_canceled()

            # Use AI to generate plan if Ollama is available
            if effective_patcher == "ollama":
                plan_text = self._ai_generate_plan(run.ticket_text, signals_text, ctx_text, profile)
            else:
                plan_text = self._simple_plan(run.ticket_text, signals_text, profile)

            path = write_artifact("plan", "plan.md", plan_text)
            self._steps.set_success(s.id, summary="Plan generated", artifact_path=path)
        else:
            if s.artifact_path and Path(s.artifact_path).exists():
                plan_text = read_text_safe(s.artifact_path)

        # ---- Step 6: Propose patch ----
        s = steps_by_name["Propose patch"]
        proposal: PatchProposal | None = None
        if s.status in {"pending", "failed"}:
            self._steps.set_running(s.id)
            ensure_not_canceled()

            patcher_used = effective_patcher
            previous_diff = None
            previous_error = None

            inv = self._store.run_dir(str(run_id)) / "invalid_patch.txt"
            if inv.exists():
                previous_error = inv.read_text(encoding="utf-8", errors="replace")[:4000]
            prev_diff_path = self._store.run_dir(str(run_id)) / "proposal.diff"
            if prev_diff_path.exists():
                previous_diff = prev_diff_path.read_text(encoding="utf-8", errors="replace")[:12000]

            context_text = ctx_text or plan_text

            try:
                if patcher_used == "ollama":
                    patcher = OllamaWorkspacePatcher(ws)
                elif patcher_used == "hf":
                    from app.services.patches import HuggingFaceWorkspacePatcher
                    patcher = HuggingFaceWorkspacePatcher(ws)
                else:
                    patcher = WorkspacePatcher(ws)

                proposal = patcher.propose(
                    run.ticket_text,
                    signals_text,
                    context_text=context_text,
                    previous_diff=previous_diff,
                    previous_error=previous_error,
                )
            except Exception as e:
                if patcher_used in {"ollama", "hf"}:
                    failed_mode = patcher_used
                    patcher_used = "rules"
                    write_artifact("fallback", "fallback_used.txt",
                                   f"{failed_mode} failed, falling back to rules patcher.\nerror={type(e).__name__}: {e}")
                    patcher = WorkspacePatcher(ws)
                    proposal = patcher.propose(
                        run.ticket_text,
                        signals_text,
                        context_text=context_text,
                        previous_diff=previous_diff,
                        previous_error=previous_error,
                    )
                else:
                    raise

            assert proposal is not None
            diff_path = write_artifact("proposal_diff", "proposal.diff", proposal.diff)
            rationale_path = write_artifact("proposal_rationale", "proposal.md",
                                             f"# {proposal.title}\n\n{proposal.rationale}\n")
            meta_path = self._store.write_json(str(run_id), "proposal.json",
                                                {"patcher_mode": patcher_used, **proposal.__dict__})
            self._artifacts.add(run_id, kind="proposal_json", path=meta_path)

            # Validate patch
            invalid = False
            invalid_reason = ""
            if patcher_used in {"ollama", "hf"}:
                rationale_lower = (proposal.rationale or "").lower()
                # Catch all variants: "still fails git apply --check", "synthesized diff still fails", etc.
                if "git apply --check" in rationale_lower and ("warning" in rationale_lower or "fails" in rationale_lower):
                    invalid = True
                    invalid_reason = proposal.rationale
            if proposal.diff.lstrip().startswith("@@"):
                invalid = True
                invalid_reason = "Patch starts with '@@' (hunk fragment) — missing file headers."

            if invalid:
                bad_path = write_artifact("invalid_patch", "invalid_patch.txt",
                                           invalid_reason or "Invalid patch format.")
                self._steps.set_failed(
                    s.id,
                    error="Invalid patch. Click 'Regenerate Patch' to retry.",
                    log_path=bad_path,
                )
                self._runs.set_status(run_id, "failed")
                return UseCaseResult(ok=False, message="Invalid patch")

            self._steps.set_success(s.id,
                                     summary=f"Patch proposed via {patcher_used}",
                                     artifact_path=rationale_path,
                                     log_path=diff_path)

        # ---- Step 7: Waiting for approval ----
        s = steps_by_name["Waiting for approval"]
        self._db.expire_all()
        run = self._runs.get(run_id)
        decision = (run.patch_approved or "no").lower() if run else "no"

        if decision != "yes":
            if s.status != "waiting":
                self._steps.set_waiting(s.id, summary="Approve or reject the proposed patch to continue.")
            self._runs.set_status(run_id, "waiting_approval")
            if decision == "rejected":
                self._steps.set_failed(s.id, error="Patch rejected by user")
                self._runs.set_status(run_id, "failed")
                return UseCaseResult(ok=False, message="Rejected")
            return UseCaseResult(ok=True, message="Waiting for approval")

        if s.status not in {"success"}:
            self._steps.set_success(s.id, summary="Approved by user")

        # ---- Step 8: Apply patch ----
        s = steps_by_name["Apply patch"]
        if s.status in {"pending", "failed"}:
            self._steps.set_running(s.id)
            ensure_not_canceled()

            self._db.expire_all()
            run = self._runs.get(run_id)
            decision = (run.patch_approved or "no").lower() if run else "no"
            if decision != "yes":
                self._steps.set_waiting(steps_by_name["Waiting for approval"].id,
                                         summary="Approval required")
                self._runs.set_status(run_id, "waiting_approval")
                return UseCaseResult(ok=True, message="Waiting for approval")

            prop_meta = self._store.run_dir(str(run_id)) / "proposal.json"
            if not prop_meta.exists():
                self._steps.set_failed(s.id, error="No proposal.json. Click 'Regenerate Patch'.")
                self._runs.set_status(run_id, "failed")
                return UseCaseResult(ok=False, message="No proposal")

            data = json.loads(prop_meta.read_text(encoding="utf-8"))
            proposal = PatchProposal(
                title=str(data.get("title", "Proposal")),
                rationale=str(data.get("rationale", "")),
                diff=str(data.get("diff", "")),
            )

            patcher_mode = str(data.get("patcher_mode", effective_patcher)).strip().lower()
            from app.services.patches import HuggingFaceWorkspacePatcher
            if patcher_mode == "ollama":
                patcher = OllamaWorkspacePatcher(ws)
            elif patcher_mode == "hf":
                patcher = HuggingFaceWorkspacePatcher(ws)
            else:
                patcher = WorkspacePatcher(ws)

            try:
                title = patcher.apply(proposal)
                path = write_artifact("apply_result", "apply_result.txt", f"Applied: {title}\n")
                self._steps.set_success(s.id, summary=f"Applied: {title}", artifact_path=path)
            except Exception as e:
                err = f"{type(e).__name__}: {e}"
                err_path = write_artifact("apply_error", "apply_error.txt", err)
                self._steps.set_failed(s.id,
                                        error="Apply failed. Use 'Retry Apply' or 'Regenerate Patch'.",
                                        log_path=err_path)
                self._runs.set_status(run_id, "failed")
                return UseCaseResult(ok=False, message="Apply failed")

        # ---- Step 9: Re-run checks ----
        s = steps_by_name["Re-run checks"]
        post_ok = True
        if s.status in {"pending", "failed"}:
            self._steps.set_running(s.id)
            ensure_not_canceled()
            cmd = profile.post or profile.baseline
            code, out, err = run_shell(cmd, timeout=settings.test_command_seconds)
            combined_output = f"$ {cmd}\n\n{out}\n{err}"
            log_path = write_artifact("post_checks_log", "post_checks.log", combined_output)

            # Detect failures: check exit code AND scan output for pytest failure markers
            # NOTE: "ERROR" alone is too broad — it matches log lines, DeprecationWarning, etc.
            # Use specific markers instead.
            import re as _re
            _has_failures_in_output = bool(
                _re.search(r"\d+ failed", combined_output)
                or "FAILED" in combined_output
                or "AssertionError" in combined_output
                or _re.search(r"^ERROR\b", combined_output, _re.MULTILINE)  # pytest ERROR collecting
            )
            _checks_failed = (code != 0) or _has_failures_in_output

            if _checks_failed:
                post_ok = False
                self._steps.set_failed(s.id,
                                        error="Post-checks still failing. Use 'Regenerate Patch'.",
                                        log_path=log_path)
                self._runs.set_patch_decision(run_id, "no")
                self._runs.set_status(run_id, "failed")
                write_artifact(
                    "next_actions", "next_actions.md",
                    "# Next actions\n\n"
                    "Post-checks failed after applying the patch.\n\n"
                    "Recommended actions:\n"
                    "- **Regenerate patch** — feeds failing log back to AI\n"
                    "- **Retry step** from 'Propose patch'\n\n"
                    "The failing output is in `post_checks.log`.\n",
                )
            else:
                self._steps.set_success(s.id, summary="All checks passed", log_path=log_path)

        # ---- Step 9b: Agentic auto-repair (if post-checks failed) ----
        # If the patch was applied but tests still fail, automatically try to regenerate
        # up to settings.max_patch_iterations additional times.
        if not post_ok:
            max_iters = max(1, int(getattr(settings, "max_patch_iterations", 2)))
            for _repair_iter in range(1, max_iters + 1):
                ensure_not_canceled()
                self._db.expire_all()
                r_check = self._runs.get(run_id)
                if not r_check or r_check.status != "failed":
                    break

                # Re-read signals from failing post_checks.log
                post_log = self._store.run_dir(str(run_id)) / "post_checks.log"
                if post_log.exists():
                    fail_out = post_log.read_text(encoding="utf-8", errors="replace")
                    new_signals = bug_detector.from_output(fail_out, "", language=getattr(profile, "language", None))
                    new_sig_text = "\n".join([f"- [{s.kind}] {s.summary}: {s.details}" for s in new_signals])
                else:
                    new_sig_text = signals_text

                # Carry over previous diff as context for the next patch
                prev_diff = (self._store.run_dir(str(run_id)) / "proposal.diff").read_text(encoding="utf-8", errors="replace")                     if (self._store.run_dir(str(run_id)) / "proposal.diff").exists() else None
                prev_err = (self._store.run_dir(str(run_id)) / "post_checks.log").read_text(encoding="utf-8", errors="replace")[:4000]                     if (self._store.run_dir(str(run_id)) / "post_checks.log").exists() else None

                write_artifact("repair_attempt", f"repair_{_repair_iter}.txt",
                               f"Auto-repair attempt {_repair_iter}/{max_iters}\n\nSignals:\n{new_sig_text}\n")

                # Reset workspace to base before re-proposing
                from app.services.run_workspaces import reset_run_workspace
                ws = reset_run_workspace(str(run_id), base_ws)

                # Re-propose patch (use refreshed ws path)
                if effective_patcher == "ollama":
                    patcher = OllamaWorkspacePatcher(ws)
                elif effective_patcher == "hf":
                    from app.services.patches import HuggingFaceWorkspacePatcher
                    patcher = HuggingFaceWorkspacePatcher(ws)
                else:
                    patcher = WorkspacePatcher(ws)

                try:
                    new_proposal = patcher.propose(
                        run.ticket_text,
                        new_sig_text,
                        context_text=ctx_text,
                        previous_diff=prev_diff,
                        previous_error=prev_err,
                    )
                except Exception as e_repair:
                    write_artifact("repair_error", f"repair_{_repair_iter}_error.txt", f"{type(e_repair).__name__}: {e_repair}")
                    break

                # Save new proposal
                write_artifact("proposal_diff", "proposal.diff", new_proposal.diff)
                write_artifact("proposal_rationale", "proposal.md", f"# {new_proposal.title}\n\n{new_proposal.rationale}\n")
                self._store.write_json(str(run_id), "proposal.json",
                                       {"patcher_mode": effective_patcher, **new_proposal.__dict__})

                # Re-apply
                try:
                    patcher.apply(new_proposal)
                except Exception as e_apply:
                    write_artifact("repair_error", f"repair_{_repair_iter}_apply_error.txt", f"{type(e_apply).__name__}: {e_apply}")
                    break

                # Re-run checks
                cmd_post = profile.post or profile.baseline
                code2, out2, err2 = run_shell(cmd_post, timeout=settings.test_command_seconds)
                combined2 = f"$ {cmd_post}\n\n{out2}\n{err2}"
                write_artifact("post_checks_log", "post_checks.log", combined2)

                import re as _re2
                _still_failing = (code2 != 0) or bool(
                    _re2.search(r"\d+ failed", combined2)
                    or "FAILED" in combined2
                    or "AssertionError" in combined2
                )
                if not _still_failing:
                    post_ok = True
                    s_post = steps_by_name["Re-run checks"]
                    self._steps.set_success(s_post.id, summary=f"All checks passed (after {_repair_iter} auto-repair(s))",
                                             log_path=self._store.run_dir(str(run_id)) / "post_checks.log")
                    self._runs.set_status(run_id, "running")
                    break

        # ---- Step 10: Smoke test ----
        s = steps_by_name["Smoke test"]
        smoke_ok = True
        if s.status in {"pending", "failed"}:
            self._steps.set_running(s.id)
            ensure_not_canceled()
            if profile.smoke:
                cmd = profile.smoke
                code, out, err = run_shell(cmd, timeout=getattr(settings, "smoke_seconds", 60))
                log_path = write_artifact("smoke_log", "smoke.log", f"$ {cmd}\n\n{out}\n{err}")
                if code != 0:
                    smoke_ok = False
                    self._steps.set_failed(s.id, error="Smoke test failed.", log_path=log_path)
                else:
                    self._steps.set_success(s.id, summary="Smoke test passed", log_path=log_path)
            else:
                self._steps.set_skipped(s.id, summary="No smoke command defined in profile")

        # ---- Step 11: Report ----
        s = steps_by_name["Report"]
        if s.status in {"pending", "failed"}:
            self._steps.set_running(s.id)
            ensure_not_canceled()
            report = self._build_report(run_id, ws, profile)
            path = write_artifact("report", "report.md", report)
            self._steps.set_success(s.id, summary="Report generated", artifact_path=path)

        final_ok = post_ok and smoke_ok
        self._runs.set_status(run_id, "completed" if final_ok else "failed")
        return UseCaseResult(ok=final_ok, message="Completed" if final_ok else "Completed with failures")

    def _ai_generate_plan(self, ticket_text: str, signals_text: str, ctx_text: str, profile) -> str:
        """Use Ollama to generate a structured plan."""
        from app.services.llm.ollama import OllamaClient
        try:
            client = OllamaClient(settings.ollama_base_url, timeout_seconds=120)
            prompt = (
                "You are a senior software engineer. Create a concise fix plan.\n\n"
                f"TICKET:\n{ticket_text}\n\n"
                f"FAILING SIGNALS:\n{signals_text}\n\n"
                f"REPO CONTEXT (snippets):\n{ctx_text[:3000]}\n\n"
                "Return a short markdown plan with sections: ## Root Cause, ## Fix Strategy, ## Files to Change\n"
                "Be specific about which functions/lines need changing. Max 400 words."
            )
            resp = client.generate(
                model=settings.ollama_model,
                prompt=prompt,
                options={"temperature": 0.1, "num_ctx": 4096},
            )
            if resp.response.strip():
                return f"# AI-Generated Plan\n\n{resp.response.strip()}\n"
        except Exception as e:
            pass  # fall back to simple plan
        return self._simple_plan(ticket_text, signals_text, profile)

    def _simple_plan(self, ticket_text: str, signals_text: str, profile) -> str:
        return (
            "# Plan\n\n"
            "## Ticket\n"
            f"{ticket_text.strip()}\n\n"
            "## Signals\n"
            f"{signals_text}\n\n"
            "## Approach\n"
            "- Identify root cause from failing test output\n"
            "- Edit minimal files to fix the issue\n"
            "- Re-run checks to verify fix\n"
            "- Produce report\n\n"
            "## Workspace profile\n"
            f"- name: {profile.name}\n"
            f"- baseline: `{profile.baseline}`\n"
            f"- post: `{profile.post or profile.baseline}`\n"
        )

    def _build_report(self, run_id: UUID, ws: str, profile) -> str:
        steps = self._steps.list_for_run(run_id)
        run_dir = self._store.run_dir(str(run_id))
        run_ws = Path(ws)

        changed_files: list[str] = []
        proposal_diff = run_dir / "proposal.diff"
        if proposal_diff.exists():
            for ln in proposal_diff.read_text(encoding="utf-8", errors="replace").splitlines():
                if ln.startswith("+++ b/"):
                    changed_files.append(ln.replace("+++ b/", "", 1).strip())

        lines: list[str] = [
            "# Spec2Ship Report",
            "",
            f"- **run_id**: `{run_id}`",
            f"- **workspace**: `{ws}`",
            f"- **profile**: `{profile.name}`" + (" _(auto-detected)_" if getattr(profile, "auto_detected", False) else ""),
            f"- **generated_at**: {datetime.utcnow().isoformat()}Z",
            "",
            "## Outcome",
            "- Report, logs, and diff are saved under the run artifacts.",
            f"- Patched source code is available in isolated run workspace: `{run_ws}`",
            "- Download ZIP (`/runs/{run_id}/download`) includes both `artifacts/` and `workspace/`.",
            "",
            "## Steps",
        ]
        for s in steps:
            status_icon = {"success": "✅", "failed": "❌", "skipped": "⏭️", "waiting": "⏳"}.get(s.status, "•")
            lines.append(f"- {s.order}. **{s.name}** {status_icon} `{s.status}`" + (f" — {s.summary}" if s.summary else ""))
            if s.error:
                lines.append(f"  - ⚠️ error: {s.error}")
            if s.log_path:
                lines.append(f"  - log: `{Path(s.log_path).name}`")
            if s.artifact_path:
                lines.append(f"  - artifact: `{Path(s.artifact_path).name}`")

        lines += ["", "## Changed files"]
        if changed_files:
            lines += [f"- `{p}`" for p in changed_files]
        else:
            lines.append("- (No code diff detected)")

        lines += [
            "",
            "## Recovery hints",
            "- If *Propose patch* failed with `invalid_patch` → click **Regenerate Patch**",
            "- If *Re-run checks* failed → open `post_checks.log` then click **Regenerate Patch**",
            "- If *Apply patch* failed → try **Regenerate Patch** or switch patcher mode",
            "",
        ]
        return "\n".join(lines)
