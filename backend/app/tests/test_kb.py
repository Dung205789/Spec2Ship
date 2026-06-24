from app.services.kb import KnowledgeBase


def test_empty_kb_returns_no_results(tmp_path):
    kb = KnowledgeBase(str(tmp_path / "kb.json"))
    kb.load()
    assert kb.search("anything") == []


def test_search_ranks_relevant_doc_first(tmp_path):
    kb = KnowledgeBase(str(tmp_path / "kb.json"))
    kb.upsert("d1", "pricing", "discount rounding uses decimal half up")
    kb.upsert("d2", "shipping", "carrier weight zones and labels")

    results = kb.search("discount rounding", k=2)
    assert results
    assert results[0].doc_id == "d1"


def test_upsert_replaces_existing_doc(tmp_path):
    kb = KnowledgeBase(str(tmp_path / "kb.json"))
    kb.upsert("d1", "t", "first version")
    kb.upsert("d1", "t", "second version about taxes")
    results = kb.search("taxes")
    assert len(results) == 1
    assert "second version" in results[0].text


def test_persistence_round_trip(tmp_path):
    path = tmp_path / "kb.json"
    kb = KnowledgeBase(str(path))
    kb.upsert("d1", "title", "persistent content about carts")
    kb.save()

    reloaded = KnowledgeBase(str(path))
    reloaded.load()
    assert reloaded.search("carts")[0].doc_id == "d1"


def test_ingest_folder_counts_markdown(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "a.md").write_text("alpha", encoding="utf-8")
    (docs / "b.md").write_text("beta", encoding="utf-8")
    (docs / "c.txt").write_text("gamma", encoding="utf-8")

    kb = KnowledgeBase(str(tmp_path / "kb.json"))
    count = kb.ingest_folder(str(docs), glob="*.md")
    assert count == 2
