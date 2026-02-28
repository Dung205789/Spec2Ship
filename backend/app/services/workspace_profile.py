from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class WorkspaceProfile:
    """Per-workspace configuration.

    Loaded from .spec2ship.yml in the workspace root.
    If no config file exists, we try to auto-detect the project type
    so any uploaded repo works without manual configuration.

    Supported keys (all optional):
      name, language
      commands:
        preflight, baseline, post, smoke
    """
    name: str = "default"
    language: str | None = None
    preflight: str | None = None
    baseline: str = "python -m pytest -vv -ra"
    post: str | None = None
    smoke: str | None = None
    auto_detected: bool = False


def _as_str(x: Any) -> str | None:
    if x is None:
        return None
    s = str(x).strip()
    return s or None


def _auto_detect_profile(root: Path) -> WorkspaceProfile:
    """Try to detect project type and build a sensible profile."""
    # Python (pytest)
    has_pytest = (
        (root / "pyproject.toml").exists() or
        (root / "setup.py").exists() or
        (root / "setup.cfg").exists() or
        any(root.rglob("test_*.py")) or
        any(root.rglob("*_test.py"))
    )
    if has_pytest:
        # Check if pytest is listed as dep
        baseline = "python -m pytest -vv -ra 2>&1 | head -200"
        preflight = "python -V && pip show pytest > /dev/null 2>&1 || pip install pytest --quiet"
        return WorkspaceProfile(
            name="auto-python",
            language="python",
            preflight=preflight,
            baseline=baseline,
            post=baseline,
            auto_detected=True,
        )

    # Node.js (jest / npm test)
    if (root / "package.json").exists():
        try:
            import json
            pkg = json.loads((root / "package.json").read_text())
            scripts = pkg.get("scripts", {})
            test_cmd = scripts.get("test", "npm test")
        except Exception:
            test_cmd = "npm test"
        return WorkspaceProfile(
            name="auto-nodejs",
            language="javascript",
            preflight="node --version && npm --version",
            baseline=f"cd /workspace && {test_cmd} 2>&1 | head -200",
            post=f"cd /workspace && {test_cmd} 2>&1 | head -200",
            auto_detected=True,
        )

    # Go
    if (root / "go.mod").exists():
        return WorkspaceProfile(
            name="auto-go",
            language="go",
            preflight="go version",
            baseline="go test ./... -v 2>&1 | head -200",
            post="go test ./... -v 2>&1 | head -200",
            auto_detected=True,
        )

    # Rust
    if (root / "Cargo.toml").exists():
        return WorkspaceProfile(
            name="auto-rust",
            language="rust",
            preflight="rustc --version",
            baseline="cargo test 2>&1 | head -200",
            post="cargo test 2>&1 | head -200",
            auto_detected=True,
        )

    # Fallback to extended detector
    return _auto_detect_profile_extended(root)


def load_workspace_profile(workspace_path: str) -> WorkspaceProfile:
    root = Path(workspace_path)

    for fname in [".spec2ship.yml", ".spec2ship.yaml"]:
        p = root / fname
        if not p.exists():
            continue
        try:
            data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        except Exception:
            break
        if not isinstance(data, dict):
            break

        name = _as_str(data.get("name") or data.get("profile")) or "custom"
        language = _as_str(data.get("language"))
        cmd_block = data.get("commands") or {}
        if not isinstance(cmd_block, dict):
            cmd_block = {}

        preflight = _as_str(cmd_block.get("preflight"))
        baseline = _as_str(cmd_block.get("baseline")) or "python -m pytest -vv -ra"
        post = _as_str(cmd_block.get("post")) or baseline
        smoke = _as_str(cmd_block.get("smoke"))

        return WorkspaceProfile(
            name=name,
            language=language,
            preflight=preflight,
            baseline=baseline,
            post=post,
            smoke=smoke,
            auto_detected=False,
        )

    # No .spec2ship.yml → auto-detect
    return _auto_detect_profile(root)


# ─── Additional language detectors (appended) ─────────────────────────────

def _auto_detect_profile_extended(root: "Path") -> "WorkspaceProfile":
    """Extended auto-detect: Java, Ruby, PHP, shell."""
    # Java (Maven / Gradle)
    if (root / "pom.xml").exists():
        return WorkspaceProfile(
            name="auto-java-maven",
            language="java",
            preflight="java -version && mvn -version",
            baseline="mvn test -q 2>&1 | tail -50",
            post="mvn test -q 2>&1 | tail -50",
            auto_detected=True,
        )
    if (root / "build.gradle").exists() or (root / "build.gradle.kts").exists():
        return WorkspaceProfile(
            name="auto-java-gradle",
            language="java",
            preflight="java -version && gradle -version",
            baseline="gradle test 2>&1 | tail -80",
            post="gradle test 2>&1 | tail -80",
            auto_detected=True,
        )

    # Ruby (RSpec / minitest)
    if (root / "Gemfile").exists():
        has_rspec = (root / ".rspec").exists() or any(root.rglob("*_spec.rb"))
        if has_rspec:
            return WorkspaceProfile(
                name="auto-ruby-rspec",
                language="ruby",
                preflight="ruby -v && bundle install --quiet",
                baseline="bundle exec rspec --format documentation 2>&1 | head -100",
                post="bundle exec rspec --format documentation 2>&1 | head -100",
                auto_detected=True,
            )
        return WorkspaceProfile(
            name="auto-ruby",
            language="ruby",
            preflight="ruby -v",
            baseline="ruby -Itest test/**/*.rb 2>&1 | head -100",
            auto_detected=True,
        )

    # PHP (PHPUnit)
    if (root / "composer.json").exists() or any(root.rglob("phpunit.xml*")):
        return WorkspaceProfile(
            name="auto-php",
            language="php",
            preflight="php -v",
            baseline="./vendor/bin/phpunit --testdox 2>&1 | head -100",
            post="./vendor/bin/phpunit --testdox 2>&1 | head -100",
            auto_detected=True,
        )

    return WorkspaceProfile(
        name="auto-unknown",
        language=None,
        preflight="echo 'No preflight configured'",
        baseline="echo 'No test command — add .spec2ship.yml to define commands.'",
        auto_detected=True,
    )
