"""OpenAIWorkspacePatcher tests using a scripted fake client (no network)."""

import json
import subprocess

from app.services.llm.openai_client import OpenAIResponse
from app.services.patches import OpenAIWorkspacePatcher


def _init_git_repo(root):
    subprocess.run(["git", "init"], cwd=root, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@local"], cwd=root, capture_output=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=root, capture_output=True)
    subprocess.run(["git", "add", "-A"], cwd=root, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init", "--allow-empty"], cwd=root, capture_output=True)


class FakeOpenAIClient:
    """Replays a scripted list of raw response strings, one per .generate() call."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.calls: list[str] = []

    def generate(self, *, model, prompt, system=None, json_mode=True, options=None):
        self.calls.append(prompt)
        return OpenAIResponse(response=self._responses.pop(0), model=model)


def _make_patcher(tmp_path, responses: list[str]) -> tuple[OpenAIWorkspacePatcher, FakeOpenAIClient]:
    patcher = OpenAIWorkspacePatcher(str(tmp_path))
    fake = FakeOpenAIClient(responses)
    patcher._openai = fake  # type: ignore[attr-defined]  # swap the real SDK client for the fake
    return patcher, fake


def test_propose_parses_valid_json_diff(tmp_path):
    (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")
    _init_git_repo(tmp_path)

    diff = (
        "diff --git a/app.py b/app.py\n"
        "--- a/app.py\n"
        "+++ b/app.py\n"
        "@@ -1 +1 @@\n"
        "-x = 1\n"
        "+x = 2\n"
    )
    response = json.dumps({"title": "Bump x", "rationale": "ticket says so", "diff": diff})

    patcher, fake = _make_patcher(tmp_path, [response])
    proposal = patcher.propose("Bump x to 2", "no failing tests")

    assert proposal.title == "Bump x"
    assert "x = 2" in proposal.diff
    assert len(fake.calls) == 1

    patcher.apply(proposal)
    assert (tmp_path / "app.py").read_text(encoding="utf-8") == "x = 2\n"


def test_propose_retries_once_on_invalid_diff(tmp_path):
    (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")
    _init_git_repo(tmp_path)

    bad = json.dumps({"title": "Bad", "rationale": "r", "diff": "@@ not a real diff @@"})
    good_diff = (
        "diff --git a/app.py b/app.py\n"
        "--- a/app.py\n"
        "+++ b/app.py\n"
        "@@ -1 +1 @@\n"
        "-x = 1\n"
        "+x = 3\n"
    )
    good = json.dumps({"title": "Fixed", "rationale": "r2", "diff": good_diff})

    patcher, fake = _make_patcher(tmp_path, [bad, good])
    proposal = patcher.propose("Bump x to 3", "no failing tests")

    assert proposal.title == "Fixed"
    assert "x = 3" in proposal.diff
    assert len(fake.calls) == 2  # first attempt + one repair round-trip


def test_propose_handles_unparseable_response(tmp_path):
    # Unparseable JSON falls back to raw-text-as-diff, which then fails
    # git apply --check and exhausts every repair/retry/fallback round-trip
    # (attempt loop + repair + full-file-synthesis fallback) without crashing.
    (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")
    _init_git_repo(tmp_path)

    patcher, fake = _make_patcher(tmp_path, ["not json at all"] * 8)
    proposal = patcher.propose("Bump x", "no failing tests")

    assert proposal.title == "LLM proposal (unparsed)"
    assert fake.calls  # at least one real call happened
