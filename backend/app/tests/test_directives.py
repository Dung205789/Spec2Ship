from app.services.directives import parse_spec2ship_directives


def test_empty_ticket_returns_no_mode():
    mode, cfg = parse_spec2ship_directives("")
    assert mode is None
    assert cfg == {}


def test_parses_mode_and_config():
    ticket = """#spec2ship: swebench_eval
    dataset=princeton-nlp/SWE-bench_Lite
    max_workers=2
    """
    mode, cfg = parse_spec2ship_directives(ticket)
    assert mode == "swebench_eval"
    assert cfg["dataset"] == "princeton-nlp/SWE-bench_Lite"
    assert cfg["max_workers"] == "2"


def test_regular_comments_are_ignored():
    ticket = "#spec2ship: train\n# this is a comment\nepochs=3"
    mode, cfg = parse_spec2ship_directives(ticket)
    assert mode == "train"
    assert cfg == {"epochs": "3"}


def test_mode_is_lowercased_and_keys_normalized():
    mode, cfg = parse_spec2ship_directives("#spec2ship: SWEBench_Eval\nMax_Workers=4")
    assert mode == "swebench_eval"
    assert cfg == {"max_workers": "4"}


def test_plain_ticket_without_directives():
    mode, cfg = parse_spec2ship_directives("Fix the failing pricing tests please.")
    assert mode is None
    assert cfg == {}
