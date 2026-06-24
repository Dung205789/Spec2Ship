from app.services.bug_detector import BugDetector


def test_pytest_failure_is_detected_with_file_hint():
    stdout = (
        "FAILED tests/test_pricing.py::test_discount - assert 895 == 896\n"
        "1 failed, 3 passed in 0.12s\n"
    )
    signals = BugDetector().from_pytest_output(stdout, "")
    kinds = {s.kind for s in signals}
    assert "test_failure" in kinds
    failure = next(s for s in signals if s.kind == "test_failure")
    assert failure.file_hint == "tests/test_pricing.py"


def test_pytest_import_error_detected():
    signals = BugDetector().from_pytest_output("", "ModuleNotFoundError: No module named 'foo'")
    assert any(s.summary == "Import error" for s in signals)


def test_jest_failure_detected():
    stdout = "FAIL src/cart.test.js\n  ● Cart › applies discount\nExpected: 896\n  Received: 895\n"
    signals = BugDetector().from_jest_output(stdout, "")
    assert any(s.kind == "test_failure" for s in signals)


def test_go_failure_detected():
    stdout = "--- FAIL: TestDiscount (0.00s)\nFAIL\n"
    signals = BugDetector().from_go_output(stdout, "")
    assert any("Go test" in s.summary for s in signals)


def test_dispatcher_routes_python_by_content():
    signals = BugDetector().from_output("FAILED tests/test_x.py::test_y - boom", "", language=None)
    assert any(s.kind == "test_failure" for s in signals)


def test_clean_output_produces_no_signals():
    assert BugDetector().from_pytest_output("3 passed in 0.01s", "") == []
