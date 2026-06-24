from app.services.diffing import snapshot_files, unified_diff


def test_unified_diff_reports_no_changes():
    snapshot = {"a.py": "print('hi')\n"}
    assert unified_diff(snapshot, snapshot) == "(no changes)"


def test_unified_diff_emits_git_header_for_apply():
    before = {"calc.py": "def f():\n    return 1\n"}
    after = {"calc.py": "def f():\n    return 2\n"}
    diff = unified_diff(before, after)
    assert "diff --git a/calc.py b/calc.py" in diff
    assert "-    return 1" in diff
    assert "+    return 2" in diff


def test_unified_diff_handles_added_and_removed_files():
    before = {"old.py": "x = 1\n"}
    after = {"new.py": "y = 2\n"}
    diff = unified_diff(before, after)
    assert "diff --git a/new.py b/new.py" in diff
    assert "diff --git a/old.py b/old.py" in diff


def test_snapshot_files_reads_only_matching_globs(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "mod.py").write_text("value = 42\n", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("ignore me\n", encoding="utf-8")

    snap = snapshot_files(str(tmp_path), ["*.py"])

    assert list(snap.values()) == ["value = 42\n"]
    assert all(rel.endswith("mod.py") for rel in snap)
