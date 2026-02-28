from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class BugSignal:
    kind: str  # "test_failure" / "lint" / "runtime" / "syntax" / "type_error" / "build"
    summary: str
    details: str
    file_hint: str = ""   # e.g. "src/cart.py:24"
    severity: str = "error"  # "error" | "warning" | "info"


class BugDetector:
    """Parse tool outputs into structured signals — multi-language support."""

    # ── Python / pytest ──────────────────────────────────────────────────────

    def from_pytest_output(self, stdout: str, stderr: str) -> list[BugSignal]:
        text = stdout + "\n" + stderr
        signals: list[BugSignal] = []

        # FAILED lines with file hint
        fails = re.findall(r"FAILED\s+(.*?)\s+-\s+(.*)", text)
        if fails:
            joined = "\n".join([f"  {a} - {b}" for a, b in fails[:20]])
            file_hint = fails[0][0].split("::")[0] if fails else ""
            signals.append(BugSignal(
                kind="test_failure",
                summary=f"{len(fails)} test(s) FAILED",
                details=joined,
                file_hint=file_hint,
                severity="error",
            ))

        # AssertionError with assertion introspection
        assert_blocks = re.findall(
            r"(AssertionError[^\n]*(?:\n(?:E\s+[^\n]+|\s+[^\n]+)){0,8})",
            text,
        )
        if assert_blocks:
            signals.append(BugSignal(
                kind="test_failure",
                summary="AssertionError",
                details=assert_blocks[0][:1000].strip(),
                severity="error",
            ))

        # ERROR collecting (import errors in test files)
        collection_errors = re.findall(r"ERROR collecting\s+(.+)", text)
        if collection_errors:
            signals.append(BugSignal(
                kind="runtime",
                summary=f"Collection error in {len(collection_errors)} file(s)",
                details="\n".join(collection_errors[:5]),
                file_hint=collection_errors[0],
                severity="error",
            ))

        # Import / ModuleNotFound
        if "ModuleNotFoundError" in text or "ImportError" in text:
            m = re.search(r"((?:ModuleNotFoundError|ImportError)[^\n]*)", text)
            signals.append(BugSignal(
                kind="runtime",
                summary="Import error",
                details=(m.group(1) if m else "ModuleNotFoundError or ImportError detected"),
                severity="error",
            ))

        # SyntaxError with file location
        syntax = re.findall(r'File "([^"]+)", line (\d+).*\n.*\nSyntaxError: (.*)', text)
        if syntax:
            f, line, msg = syntax[0]
            signals.append(BugSignal(
                kind="syntax",
                summary=f"SyntaxError: {msg.strip()}",
                details=f"File: {f}, line {line}",
                file_hint=f"{f}:{line}",
                severity="error",
            ))
        elif "SyntaxError" in text:
            m = re.search(r"(SyntaxError[^\n]*)", text)
            if m:
                signals.append(BugSignal(kind="syntax", summary="SyntaxError", details=m.group(1)[:300], severity="error"))

        # TypeError, ValueError, AttributeError, KeyError, RuntimeError, NameError
        for exc in ["TypeError", "ValueError", "AttributeError", "KeyError", "RuntimeError", "NameError", "IndexError"]:
            if exc in text:
                m = re.search(rf"({exc}[^\n]*)", text)
                if m:
                    # Find file hint
                    fh = ""
                    ctx = re.search(r'File "([^"]+)", line (\d+).*\n.*\n.*' + exc, text)
                    if ctx:
                        fh = f"{ctx.group(1)}:{ctx.group(2)}"
                    signals.append(BugSignal(kind="runtime", summary=exc, details=m.group(1)[:400], file_hint=fh, severity="error"))
                    break  # one is enough for the first exception

        # Flake8 / ruff lint
        lint_lines = re.findall(r"([^\s:]+\.py):(\d+):(\d+):\s+(E\d+|W\d+|F\d+)\s+(.*)", text)
        if lint_lines:
            details = "\n".join([f"{f}:{l}:{c} {code} {msg}" for f, l, c, code, msg in lint_lines[:10]])
            signals.append(BugSignal(
                kind="lint",
                summary=f"{len(lint_lines)} lint issue(s)",
                details=details,
                file_hint=lint_lines[0][0],
                severity="warning",
            ))

        # Mypy type errors
        mypy = re.findall(r"([^\s:]+\.py):(\d+): (error|note): (.*)", text)
        if mypy:
            errs = [(f, l, m) for f, l, t, m in mypy if t == "error"]
            if errs:
                signals.append(BugSignal(
                    kind="type_error",
                    summary=f"{len(errs)} mypy error(s)",
                    details="\n".join([f"{f}:{l}: {m}" for f, l, m in errs[:10]]),
                    file_hint=errs[0][0],
                    severity="error",
                ))

        # Generic: short summary
        short_summary = re.search(r"(\d+\s+failed(?:,\s*\d+\s+passed)?(?:,\s*\d+\s+error)?)", text)
        if short_summary and not signals:
            signals.append(BugSignal(kind="test_failure", summary="Tests failed", details=short_summary.group(1), severity="error"))

        # Fallback
        if not signals and ("fail" in text.lower() or "error" in text.lower()):
            signals.append(BugSignal(
                kind="test_failure",
                summary="Tests failed (see details)",
                details=text.strip()[-3000:],
                severity="error",
            ))

        return signals

    # ── JavaScript / TypeScript / Jest / Vitest / Mocha ───────────────────

    def from_jest_output(self, stdout: str, stderr: str) -> list[BugSignal]:
        text = stdout + "\n" + stderr
        signals: list[BugSignal] = []

        # FAIL / PASS summary
        fail_files = re.findall(r"^\s*FAIL\s+(.+)", text, re.MULTILINE)
        if fail_files:
            signals.append(BugSignal(
                kind="test_failure",
                summary=f"{len(fail_files)} test file(s) FAILED",
                details="\n".join(fail_files[:10]),
                file_hint=fail_files[0],
                severity="error",
            ))

        # ● Test name: description
        test_fails = re.findall(r"●\s+(.+)", text)
        if test_fails:
            signals.append(BugSignal(
                kind="test_failure",
                summary=f"{len(test_fails)} test(s) failed",
                details="\n".join(test_fails[:10]),
                severity="error",
            ))

        # expect(...).toBe(...) failures
        expect_fails = re.findall(r"(Expected:.*\n\s*Received:.*)", text)
        if expect_fails:
            signals.append(BugSignal(kind="test_failure", summary="Assertion mismatch", details=expect_fails[0][:400], severity="error"))

        # TypeError / ReferenceError
        for exc in ["TypeError", "ReferenceError", "SyntaxError"]:
            m = re.search(rf"({exc}: [^\n]+)", text)
            if m:
                fh = ""
                ctx = re.search(r"at .+ \(([^)]+):(\d+):\d+\)", text)
                if ctx:
                    fh = f"{ctx.group(1)}:{ctx.group(2)}"
                signals.append(BugSignal(kind="runtime", summary=exc, details=m.group(1)[:400], file_hint=fh, severity="error"))
                break

        # TS type errors (tsc)
        ts_errs = re.findall(r"([\w./\\-]+\.tsx?)\((\d+),\d+\): error TS\d+: (.*)", text)
        if ts_errs:
            signals.append(BugSignal(
                kind="type_error",
                summary=f"{len(ts_errs)} TypeScript error(s)",
                details="\n".join([f"{f}:{l}: {m}" for f, l, m in ts_errs[:10]]),
                file_hint=ts_errs[0][0],
                severity="error",
            ))

        if not signals and ("fail" in text.lower() or "error" in text.lower()):
            signals.append(BugSignal(kind="test_failure", summary="Tests/build failed", details=text.strip()[-2000:], severity="error"))

        return signals

    # ── Go ────────────────────────────────────────────────────────────────

    def from_go_output(self, stdout: str, stderr: str) -> list[BugSignal]:
        text = stdout + "\n" + stderr
        signals: list[BugSignal] = []

        go_fails = re.findall(r"--- FAIL:\s+(\S+)\s+\((.+?)\)", text)
        if go_fails:
            signals.append(BugSignal(
                kind="test_failure",
                summary=f"{len(go_fails)} Go test(s) FAILED",
                details="\n".join([f"{n} ({d})" for n, d in go_fails[:10]]),
                severity="error",
            ))

        compile_errs = re.findall(r"([\w./\\-]+\.go):(\d+):\d+: (.*)", text)
        if compile_errs:
            signals.append(BugSignal(
                kind="syntax",
                summary=f"{len(compile_errs)} compile error(s)",
                details="\n".join([f"{f}:{l}: {m}" for f, l, m in compile_errs[:10]]),
                file_hint=compile_errs[0][0],
                severity="error",
            ))

        if not signals and ("FAIL" in text or "fail" in text.lower()):
            signals.append(BugSignal(kind="test_failure", summary="Go tests failed", details=text.strip()[-2000:], severity="error"))

        return signals

    # ── Rust ──────────────────────────────────────────────────────────────

    def from_cargo_output(self, stdout: str, stderr: str) -> list[BugSignal]:
        text = stdout + "\n" + stderr
        signals: list[BugSignal] = []

        cargo_fails = re.findall(r"test (.+) \.\.\. FAILED", text)
        if cargo_fails:
            signals.append(BugSignal(
                kind="test_failure",
                summary=f"{len(cargo_fails)} Rust test(s) FAILED",
                details="\n".join(cargo_fails[:10]),
                severity="error",
            ))

        errors = re.findall(r"error(?:\[E\d+\])?: (.*)", text)
        if errors:
            signals.append(BugSignal(kind="syntax", summary=f"{len(errors)} Rust compile error(s)", details="\n".join(errors[:5]), severity="error"))

        if not signals and "FAILED" in text:
            signals.append(BugSignal(kind="test_failure", summary="Cargo test failed", details=text.strip()[-2000:], severity="error"))

        return signals

    # ── Generic dispatcher ────────────────────────────────────────────────

    def from_output(self, stdout: str, stderr: str, language: str | None = None) -> list[BugSignal]:
        """Dispatch to the right parser based on detected language/output."""
        text = stdout + "\n" + stderr

        # Detect by content
        if "pytest" in text or "PASSED" in text or "FAILED" in text and ".py" in text:
            return self.from_pytest_output(stdout, stderr)
        if "FAIL\t" in text or "--- FAIL:" in text or ".go:" in text:
            return self.from_go_output(stdout, stderr)
        if "cargo" in text.lower() or ".rs:" in text:
            return self.from_cargo_output(stdout, stderr)
        if "jest" in text.lower() or "vitest" in text.lower() or "mocha" in text.lower() or ".tsx" in text or ".ts:" in text:
            return self.from_jest_output(stdout, stderr)

        # Language hint
        if language == "python":
            return self.from_pytest_output(stdout, stderr)
        if language == "go":
            return self.from_go_output(stdout, stderr)
        if language in {"javascript", "typescript"}:
            return self.from_jest_output(stdout, stderr)
        if language == "rust":
            return self.from_cargo_output(stdout, stderr)

        # Fallback: generic
        return self.from_pytest_output(stdout, stderr)

    # Legacy
    def from_generic_output(self, output: str) -> list[BugSignal]:
        return self.from_output(output, "")
