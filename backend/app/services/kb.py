from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from rank_bm25 import BM25Okapi


def _tokenize(text: str) -> list[str]:
    # Simple tokenizer: lowercase words + numbers
    return re.findall(r"[a-z0-9_\-]+", text.lower())


@dataclass(frozen=True)
class KbDoc:
    doc_id: str
    title: str
    text: str


class KnowledgeBase:
    """A tiny local knowledge base using BM25 (no heavy models required).

    Important: BM25Okapi from rank_bm25 is not safe with an empty corpus (it can
    raise ZeroDivisionError). We treat "no documents" as a first-class state and
    simply return no results for search().
    """

    def __init__(self, store_path: str) -> None:
        self._store_path = Path(store_path)
        self._docs: list[KbDoc] = []
        self._bm25: BM25Okapi | None = None

    def load(self) -> None:
        if not self._store_path.exists():
            self._docs = []
            self._bm25 = None
            return

        data = json.loads(self._store_path.read_text(encoding="utf-8"))
        self._docs = [KbDoc(**d) for d in data.get("docs", [])]
        self._rebuild()

    def save(self) -> None:
        payload = {"docs": [d.__dict__ for d in self._docs]}
        self._store_path.parent.mkdir(parents=True, exist_ok=True)
        self._store_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def ingest_folder(self, folder: str, glob: str = "*.md") -> int:
        base = Path(folder)
        count = 0
        for p in base.rglob(glob):
            if not p.is_file():
                continue
            doc_id = str(p)
            title = p.name
            text = p.read_text(encoding="utf-8")
            self.upsert(doc_id=doc_id, title=title, text=text)
            count += 1
        self.save()
        return count

    def upsert(self, doc_id: str, title: str, text: str) -> None:
        for i, d in enumerate(self._docs):
            if d.doc_id == doc_id:
                self._docs[i] = KbDoc(doc_id=doc_id, title=title, text=text)
                self._rebuild()
                return
        self._docs.append(KbDoc(doc_id=doc_id, title=title, text=text))
        self._rebuild()

    def search(self, query: str, k: int = 4) -> list[KbDoc]:
        # No docs => no results (and avoid BM25 initialization issues).
        if not self._docs:
            return []

        tokens = _tokenize(query)
        if not tokens:
            return []

        if self._bm25 is None:
            self._rebuild()

        if self._bm25 is None:
            return []

        scores = self._bm25.get_scores(tokens)
        ranked = sorted(range(len(self._docs)), key=lambda i: scores[i], reverse=True)[:k]
        return [self._docs[i] for i in ranked]

    def _rebuild(self) -> None:
        # rank_bm25 can crash on degenerate corpora; keep it defensive.
        corpus = [_tokenize(d.text) for d in self._docs if d.text.strip()]
        if not corpus:
            self._bm25 = None
            return

        try:
            self._bm25 = BM25Okapi(corpus)
            # Some degenerate cases can still yield empty idf and crash later.
            if not getattr(self._bm25, "idf", None):
                self._bm25 = None
        except ZeroDivisionError:
            self._bm25 = None
