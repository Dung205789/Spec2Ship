"""
Spec2Ship Integration Tests
Run from spec2ship_v3 directory.

Windows PowerShell:
    $env:API_URL="http://localhost:8000"
    pytest test_spec2ship.py -m smoke -v -s

    $env:PATCHER_MODE="rules"
    pytest test_spec2ship.py -m rules -v -s

    $env:PATCHER_MODE="ollama"
    $env:POLL_TIMEOUT="600"
    pytest test_spec2ship.py -m ollama -v -s

Linux/Mac:
    pytest test_spec2ship.py -m smoke -v -s
    PATCHER_MODE=rules pytest test_spec2ship.py -m rules -v -s

IMPORTANT - Correct API endpoints:
    Health : GET  /healthz          (NOT /health)
    Runs   : POST /runs/            (NO /api prefix)
    Steps  : GET  /runs/{id}/steps
"""
from __future__ import annotations
import os
import time
import pytest
import requests

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
API_URL       = os.getenv("API_URL",       "http://localhost:8000")
PATCHER_MODE  = os.getenv("PATCHER_MODE",  "rules")
POLL_TIMEOUT  = int(os.getenv("POLL_TIMEOUT",  "180"))
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "3"))

RUNS_URL = f"{API_URL}/runs"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def create_run(title, ticket, workspace=""):
    r = requests.post(
        f"{RUNS_URL}/",
        json={"title": title, "ticket_text": ticket, "workspace": workspace},
        timeout=10,
    )
    assert r.status_code == 200, f"create_run -> {r.status_code}: {r.text[:200]}"
    return r.json()


def delete_run(run_id):
    try:
        requests.post(f"{RUNS_URL}/{run_id}/delete", timeout=10)
    except Exception:
        pass


def get_run(run_id):
    r = requests.get(f"{RUNS_URL}/{run_id}", timeout=10)
    assert r.status_code == 200
    return r.json()


def get_steps(run_id):
    r = requests.get(f"{RUNS_URL}/{run_id}/steps", timeout=10)
    assert r.status_code == 200
    return r.json()


def get_log(run_id, kind):
    r = requests.get(f"{RUNS_URL}/{run_id}/live_log", params={"kind": kind}, timeout=10)
    if r.status_code == 200:
        d = r.json()
        return d.get("content") if d.get("found") else None
    return None


def start_run(run_id):
    r = requests.post(f"{RUNS_URL}/{run_id}/start", timeout=10)
    assert r.status_code == 200, f"start -> {r.status_code}: {r.text[:100]}"


def switch_patcher(run_id, mode):
    r = requests.post(f"{RUNS_URL}/{run_id}/switch_patcher", params={"mode": mode}, timeout=5)
    assert r.status_code == 200, f"switch_patcher -> {r.status_code}"


def approve_patch(run_id):
    r = requests.post(f"{RUNS_URL}/{run_id}/patch_decision", params={"decision": "yes"}, timeout=10)
    assert r.status_code == 200, f"approve -> {r.status_code}"


def poll_run(run_id, stop_on_approval=False, timeout=None):
    """Poll until terminal status or waiting_approval. Returns run dict."""
    terminal = {"completed", "failed", "canceled"}
    deadline = time.time() + (timeout or POLL_TIMEOUT)
    last = "?"
    while time.time() < deadline:
        run = get_run(run_id)
        last = run["status"]
        if last in terminal:
            return run
        if stop_on_approval and last == "waiting_approval":
            return run
        time.sleep(POLL_INTERVAL)
    pytest.fail(f"Timeout {timeout or POLL_TIMEOUT}s -> last status: {last}")


def print_steps(run_id):
    steps = get_steps(run_id)
    icons = {"success": "OK  ", "failed": "FAIL", "waiting": "WAIT",
             "running": "RUN ", "skipped": "SKIP", "pending": ".... "}
    print(f"\n  {'':2} {'Step':<30} {'Status':<15} Info")
    print(f"  {'-'*68}")
    for s in steps:
        icon = icons.get(s["status"], "    ")
        info = (s.get("summary") or s.get("error") or "")[:38]
        print(f"  [{icon}] {s['name']:<30} {s['status']:<15} {info}")


# ---------------------------------------------------------------------------
# Markers + API readiness fixture
# ---------------------------------------------------------------------------

def pytest_configure(config):
    config.addinivalue_line("markers", "smoke: fast API tests, no pipeline (~10s)")
    config.addinivalue_line("markers", "rules: rules patcher tests (~2-3 min)")
    config.addinivalue_line("markers", "ollama: ollama LLM tests (~5-10 min)")


@pytest.fixture(autouse=True)
def ensure_api():
    """Wait up to 30s for API. Fails with clear message if not reachable."""
    health_url = f"{API_URL}/healthz"   # NOTE: /healthz not /health
    for _ in range(10):
        try:
            r = requests.get(health_url, timeout=3)
            if r.status_code == 200:
                return
        except Exception:
            pass
        time.sleep(3)
    pytest.fail(
        f"\n"
        f"  API not reachable at: {health_url}\n"
        f"\n"
        f"  Fix: make sure Docker containers are running:\n"
        f"    docker compose up -d --build\n"
        f"\n"
        f"  Then wait ~15 seconds for the API to start, then retry.\n"
        f"\n"
        f"  Check container status:\n"
        f"    docker compose ps\n"
        f"\n"
        f"  Check API logs:\n"
        f"    docker compose logs api --tail=50\n"
    )


# ===========================================================================
# SMOKE TESTS  (~10 seconds)
# No pipeline runs -> just checks API is alive and endpoints work.
# ===========================================================================

@pytest.mark.smoke
class TestSmoke:
    """
    Fast API sanity checks. Completes in ~10 seconds.
    Does NOT run any pipeline.

    Expected results:
      GET /healthz                -> 200 {"status": "ok"}
      POST /runs/ + DELETE        -> create and delete a run
      11 steps in correct order   after starting a run
      switch_patcher rules/ollama/hf -> 200 each
      decision='maybe'            -> 422 rejected
      GET /docs                   -> 200
    """

    def test_healthz(self):
        r = requests.get(f"{API_URL}/healthz", timeout=5)
        assert r.status_code == 200, f"Expected 200, got {r.status_code}"
        body = r.json()
        assert body.get("status") == "ok", f"Expected status=ok, got {body}"
        print(f"\n  [OK] GET /healthz -> {body}")
        print(f"       Web UI  : http://localhost:3000")
        print(f"       API docs: {API_URL}/docs")

    def test_create_delete_run(self):
        run = create_run("[Smoke] ephemeral run", "test ticket content")
        rid = run["id"]
        assert run["status"] in ("pending", "created"), f"New run should be pending/created, got {run['status']}"
        delete_run(rid)
        r = requests.get(f"{RUNS_URL}/{rid}", timeout=5)
        assert r.status_code == 404, f"After delete should be 404, got {r.status_code}"
        print(f"\n  [OK] create -> delete -> 404 confirmed")

    def test_steps_initialized_correctly(self):
        run = create_run("[Smoke] steps init check", "test ticket content")
        rid = run["id"]
        try:
            start_run(rid)
            time.sleep(5)  # let worker initialize steps
            steps = get_steps(rid)
            names = [s["name"] for s in steps]
            expected = [
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
            assert names == expected, (
                f"\n  Got:      {names}"
                f"\n  Expected: {expected}"
            )
            print(f"\n  [OK] 11 steps in correct order")
        finally:
            requests.post(f"{RUNS_URL}/{rid}/cancel", timeout=5)
            time.sleep(1)
            delete_run(rid)

    def test_switch_patcher_all_modes(self):
        run = create_run("[Smoke] switch patcher", "test")
        rid = run["id"]
        try:
            for mode in ["rules", "ollama", "hf"]:
                r = requests.post(
                    f"{RUNS_URL}/{rid}/switch_patcher",
                    params={"mode": mode},
                    timeout=5,
                )
                assert r.status_code == 200, (
                    f"switch_patcher(mode={mode}) -> {r.status_code}: {r.text[:100]}"
                )
            print(f"\n  [OK] switch_patcher: rules / ollama / hf all accepted")
        finally:
            delete_run(rid)

    def test_invalid_decision_rejected(self):
        run = create_run("[Smoke] bad decision", "test")
        rid = run["id"]
        try:
            r = requests.post(
                f"{RUNS_URL}/{rid}/patch_decision",
                params={"decision": "maybe"},
                timeout=5,
            )
            assert r.status_code == 422, (
                f"Expected 422 for decision='maybe', got {r.status_code}: {r.text[:100]}"
            )
            print(f"\n  [OK] invalid decision 'maybe' -> 422")
        finally:
            delete_run(rid)

    def test_swagger_docs(self):
        r = requests.get(f"{API_URL}/docs", timeout=5)
        assert r.status_code == 200, f"Expected 200, got {r.status_code}"
        print(f"\n  [OK] Swagger UI reachable at {API_URL}/docs")


# ===========================================================================
# RULES PATCHER TESTS  (~2-3 minutes each)
# Requires: docker compose up, sample_workspace with known bugs.
# Before running: click "Reset sample" on http://localhost:3000
#                 or run: docker compose exec api python -m app.scripts.reset
# ===========================================================================

TICKET_DISCOUNT = (
    "Fix discount rounding bug\n"
    "\n"
    "apply_discount() uses int() which floors fractional cents.\n"
    "Must use half-up rounding per spec.\n"
    "\n"
    "Failing: 995 cents at 10% discount -> expected 896, got 895\n"
    "Tests: test_discount_rounding_over_http, test_percent_is_clamped\n"
)

TICKET_HEALTH = (
    "Add /health endpoint\n"
    "\n"
    "Need GET /health -> 200 {\"status\": \"ok\"} for load balancer.\n"
    "Must not break existing /discount endpoint.\n"
)


@pytest.mark.rules
class TestRulesDiscountFix:
    """
    Full pipeline with rules patcher: detect -> propose -> approve -> verify.

    Setup: PATCHER_MODE=rules (default, no Ollama needed)
    Before running: reset sample workspace on http://localhost:3000

    Expected:
      1. Pipeline stops at waiting_approval
      2. Diff starts with 'diff --git' (header fix applied)
      3. Diff references pricing.py / apply_discount
      4. After approve: Re-run checks = success
      5. Run status = completed
      6. View result at http://localhost:3000/runs/<id>
    """
    _rid = None

    def teardown_method(self, _):
        if self.__class__._rid:
            delete_run(self.__class__._rid)
            self.__class__._rid = None

    def test_full_pipeline(self):
        run = create_run("[Rules] Fix discount rounding", TICKET_DISCOUNT)
        rid = run["id"]
        self.__class__._rid = rid

        switch_patcher(rid, "rules")
        start_run(rid)
        print(f"\n  Run URL: http://localhost:3000/runs/{rid}")

        # Wait for approval gate
        run = poll_run(rid, stop_on_approval=True, timeout=120)
        print_steps(rid)

        assert run["status"] == "waiting_approval", (
            f"Expected waiting_approval, got: {run['status']}\n"
            f"  Tip: Reset sample workspace on http://localhost:3000 first"
        )

        # Check diff format (bug fix #6 verification)
        diff = get_log(rid, "proposal_diff") or ""
        print(f"\n  --- Diff preview (first 300 chars) ---")
        print(f"  {diff[:300]}")
        print(f"  --- end ---")

        assert diff, "Expected a non-empty diff"
        assert diff.startswith("diff --git"), (
            f"Diff must start with 'diff --git' header.\n"
            f"  Got: {diff[:80]}\n"
            f"  (Bug fix #6 in diffing.py should have added this header)"
        )
        assert any(kw in diff for kw in ("pricing.py", "apply_discount")), (
            "Diff must reference pricing.py or apply_discount"
        )

        # Approve and wait for completion
        approve_patch(rid)
        run = poll_run(rid, timeout=POLL_TIMEOUT)
        print_steps(rid)

        steps = {s["name"]: s for s in get_steps(rid)}

        assert run["status"] == "completed", (
            f"Run must be completed, got: {run['status']}\n"
            f"  Re-run checks error: {steps.get('Re-run checks', {}).get('error', '')}\n"
            f"  Post-check log:\n{get_log(rid, 'post_checks_log') or '(empty)'}"
        )
        assert steps["Re-run checks"]["status"] == "success", (
            f"Re-run checks failed: {steps['Re-run checks'].get('error', '')}"
        )

        print(f"\n  [PASS] Discount fix verified")
        print(f"         View: http://localhost:3000/runs/{rid}")


@pytest.mark.rules
class TestRulesHealthEndpoint:
    """
    Pipeline: add /health endpoint ticket.

    Expected:
      1. Pipeline stops at waiting_approval
      2. After approve: Apply patch = success
      3. Re-run checks = success
      4. Run completed
    """
    _rid = None

    def teardown_method(self, _):
        if self.__class__._rid:
            delete_run(self.__class__._rid)
            self.__class__._rid = None

    def test_add_health(self):
        run = create_run("[Rules] Add /health endpoint", TICKET_HEALTH)
        rid = run["id"]
        self.__class__._rid = rid

        switch_patcher(rid, "rules")
        start_run(rid)
        print(f"\n  Run URL: http://localhost:3000/runs/{rid}")

        run = poll_run(rid, stop_on_approval=True, timeout=120)
        print_steps(rid)
        assert run["status"] == "waiting_approval", f"Got: {run['status']}"

        approve_patch(rid)
        run = poll_run(rid, timeout=POLL_TIMEOUT)
        print_steps(rid)

        steps = {s["name"]: s for s in get_steps(rid)}
        assert run["status"] == "completed", f"Got: {run['status']}"
        assert steps["Apply patch"]["status"] == "success"
        assert steps["Re-run checks"]["status"] == "success"

        print(f"\n  [PASS] Health endpoint added")
        print(f"         View: http://localhost:3000/runs/{rid}")


@pytest.mark.rules
class TestRegenResetsWorkspace:
    """
    Verifies bug fix #1: regenerate_patch resets workspace before retrying.

    Old bug: regenerate did NOT reset workspace -> new patch applied on top
             of already-modified code -> duplicate definitions -> always failed.

    Expected:
      1. Pipeline reaches waiting_approval
      2. Call regenerate_patch -> run goes back to waiting_approval (workspace reset)
      3. After second approve: Apply patch has NO 'duplicate' or 'already' error
      4. Run completed
    """
    _rid = None

    def teardown_method(self, _):
        if self.__class__._rid:
            delete_run(self.__class__._rid)
            self.__class__._rid = None

    def test_regen_resets_workspace(self):
        run = create_run("[Rules] Regen resets workspace", TICKET_DISCOUNT)
        rid = run["id"]
        self.__class__._rid = rid

        switch_patcher(rid, "rules")
        start_run(rid)
        print(f"\n  Run URL: http://localhost:3000/runs/{rid}")

        # First proposal
        run = poll_run(rid, stop_on_approval=True, timeout=120)
        assert run["status"] == "waiting_approval"
        print(f"\n  First proposal ready. Calling regenerate_patch...")

        # Trigger regenerate (must reset workspace internally)
        r = requests.post(f"{RUNS_URL}/{rid}/regenerate_patch", timeout=10)
        assert r.status_code == 200, f"regenerate_patch -> {r.status_code}: {r.text[:100]}"

        # Second proposal
        run = poll_run(rid, stop_on_approval=True, timeout=120)
        print_steps(rid)
        assert run["status"] == "waiting_approval", (
            f"After regen expected waiting_approval, got: {run['status']}"
        )
        print(f"\n  Second proposal ready (workspace was reset). Approving...")

        approve_patch(rid)
        run = poll_run(rid, timeout=POLL_TIMEOUT)
        print_steps(rid)

        steps = {s["name"]: s for s in get_steps(rid)}
        apply_err = (steps.get("Apply patch", {}).get("error") or "").lower()

        assert "duplicate" not in apply_err, (
            f"Workspace contamination! Apply patch error contains 'duplicate':\n  {apply_err}"
        )
        assert "already" not in apply_err, (
            f"Workspace contamination! Apply patch error contains 'already':\n  {apply_err}"
        )
        assert run["status"] == "completed", f"Got: {run['status']}"

        print(f"\n  [PASS] Regenerate correctly reset workspace")
        print(f"         View: http://localhost:3000/runs/{rid}")


# ===========================================================================
# OLLAMA TESTS  (~5-10 minutes)
# Only runs when PATCHER_MODE=ollama
# ===========================================================================

@pytest.mark.ollama
@pytest.mark.skipif(
    os.getenv("PATCHER_MODE", "rules") != "ollama",
    reason="Set $env:PATCHER_MODE='ollama' to enable Ollama tests",
)
class TestOllamaDiscountFix:
    """
    LLM-based patch with Ollama.

    Setup (Windows PowerShell):
      $env:PATCHER_MODE="ollama"
      $env:POLL_TIMEOUT="600"
      docker compose -f docker-compose.yml -f docker-compose.llm.yml up -d

    Expected:
      1. Ollama generates valid unified diff
      2. git apply --check passes
      3. Re-run checks = success
    """
    _rid = None

    def teardown_method(self, _):
        if self.__class__._rid:
            delete_run(self.__class__._rid)
            self.__class__._rid = None

    def test_ollama_patch(self):
        # Check Ollama is reachable
        try:
            r = requests.get("http://localhost:11434/api/tags", timeout=3)
            if r.status_code != 200:
                pytest.skip("Ollama not reachable at localhost:11434")
        except Exception:
            pytest.skip("Ollama not reachable at localhost:11434")

        run = create_run("[Ollama] Fix discount rounding", TICKET_DISCOUNT)
        rid = run["id"]
        self.__class__._rid = rid

        switch_patcher(rid, "ollama")
        start_run(rid)
        print(f"\n  Run URL: http://localhost:3000/runs/{rid}")
        print(f"  Waiting for Ollama to generate patch (2-5 min)...")

        run = poll_run(rid, stop_on_approval=True, timeout=POLL_TIMEOUT)

        # If proposal failed, try one regenerate
        if run["status"] == "failed":
            steps = {s["name"]: s for s in get_steps(rid)}
            if steps.get("Propose patch", {}).get("status") == "failed":
                print(f"  Proposal failed, calling regenerate_patch...")
                requests.post(f"{RUNS_URL}/{rid}/regenerate_patch", timeout=10)
                run = poll_run(rid, stop_on_approval=True, timeout=POLL_TIMEOUT)

        print_steps(rid)
        assert run["status"] == "waiting_approval", f"Got: {run['status']}"

        diff = get_log(rid, "proposal_diff") or ""
        print(f"\n  Diff (first 400):\n  {diff[:400]}\n")
        assert "@@" in diff, "Diff must contain hunk headers (@@)"

        approve_patch(rid)
        run = poll_run(rid, timeout=POLL_TIMEOUT)
        print_steps(rid)

        steps = {s["name"]: s for s in get_steps(rid)}
        assert steps["Re-run checks"]["status"] == "success", (
            f"Post-checks failed: {steps['Re-run checks'].get('error', '')}"
        )
        print(f"\n  [PASS] Ollama patch verified")
        print(f"         View: http://localhost:3000/runs/{rid}")


# ===========================================================================
# Terminal summary
# ===========================================================================

def pytest_terminal_summary(terminalreporter, exitstatus, config):
    p = len(terminalreporter.stats.get("passed", []))
    f = len(terminalreporter.stats.get("failed", []))
    e = len(terminalreporter.stats.get("error",  []))
    print(f"\n"
          f"  +--------------------------------------------------+\n"
          f"  |  Spec2Ship Results                               |\n"
          f"  +--------------------------------------------------+\n"
          f"  |  Passed : {p:<40}|\n"
          f"  |  Failed : {f:<40}|\n"
          f"  |  Errors : {e:<40}|\n"
          f"  +--------------------------------------------------+\n"
          f"  |  Web UI  : http://localhost:3000                 |\n"
          f"  |  API docs: http://localhost:8000/docs            |\n"
          f"  |  Patcher : {PATCHER_MODE:<38}  |\n"
          f"  +--------------------------------------------------+")
