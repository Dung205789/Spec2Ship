from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "into", "when", "then",
    "than", "have", "has", "had", "will", "would", "should", "could", "cant",
    "cannot", "not", "your", "you", "our", "are", "is", "was", "were", "be",
    "being", "been", "it", "in", "on", "to", "of", "a", "an", "as", "at",
    "by", "or", "if", "else", "true", "false",
}

_SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".venv", "venv", "env",
    "dist", "build", ".next", ".nuxt", ".output", "coverage",
    ".pytest_cache", ".mypy_cache", "htmlcov", ".tox", ".eggs",
}

_SKIP_SUFFIXES = {
    ".pyc", ".pyo", ".so", ".dylib", ".dll", ".class", ".jar",
    ".ico", ".png", ".jpg", ".jpeg", ".gif", ".woff", ".woff2",
    ".ttf", ".eot", ".zip", ".tar", ".gz", ".pdf", ".db", ".sqlite",
    ".lock",
}


@dataclass(frozen=True)
class Snippet:
    path: str
    score: int
    excerpt: str
    language: str = ""


def _pick_keywords(text: str, max_keywords: int = 15) -> list[str]:
    tokens = re.findall(r"[a-zA-Z_][a-zA-Z0-9_]{2,}", text.lower())
    freq: dict[str, int] = {}
    for t in tokens:
        if t not in _STOPWORDS:
            freq[t] = freq.get(t, 0) + 1
    ranked = sorted(freq.items(), key=lambda kv: (kv[1], len(kv[0])), reverse=True)
    return [k for k, _ in ranked[:max_keywords]]


def _extract_file_hints(text: str) -> list[str]:
    candidates = re.findall(r"([\w./-]+\.(?:py|js|ts|tsx|jsx|toml|cfg|ini|yaml|yml|json))", text)
    seen: set[str] = set()
    out: list[str] = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out[:30]


def _detect_language(path: Path) -> str:
    ext = path.suffix.lower()
    return {
        ".py": "python", ".js": "javascript", ".ts": "typescript",
        ".tsx": "tsx", ".jsx": "jsx", ".go": "go", ".rs": "rust",
        ".java": "java", ".rb": "ruby", ".php": "php",
        ".cs": "csharp", ".cpp": "cpp", ".c": "c",
        ".toml": "toml", ".yaml": "yaml", ".yml": "yaml",
        ".json": "json", ".sh": "bash", ".md": "markdown",
    }.get(ext, "")


def _should_skip(p: Path, root: Path) -> bool:
    try:
        rel = p.relative_to(root)
        for part in rel.parts[:-1]:
            if part in _SKIP_DIRS or part.startswith("."):
                return True
    except ValueError:
        return True
    if p.suffix.lower() in _SKIP_SUFFIXES:
        return True
    if p.name.endswith(".min.js") or p.name.endswith(".bundle.js"):
        return True
    return False


def _best_excerpt(content: str, keywords: list[str], context_lines: int = 60) -> str:
    lines = content.splitlines()
    if not lines:
        return ""
    lower = content.lower()
    window = min(context_lines * 2, len(lines))

    best_start = 0
    best_density = 0
    step = max(1, window // 2)
    for start in range(0, max(1, len(lines) - window), step):
        chunk = "\n".join(lines[start:start + window]).lower()
        density = sum(chunk.count(kw) for kw in keywords)
        if density > best_density:
            best_density = density
            best_start = start

    start = max(0, best_start)
    end = min(len(lines), start + window)
    return "\n".join(lines[start:end])


def _workspace_tree(root: Path, max_entries: int = 60) -> str:
    lines: list[str] = []
    try:
        for item in sorted(root.iterdir()):
            if item.name.startswith(".") or item.name in _SKIP_DIRS:
                continue
            if item.is_dir():
                lines.append(f"  {item.name}/")
                try:
                    for sub in sorted(item.iterdir())[:8]:
                        if sub.name.startswith(".") or sub.name in _SKIP_DIRS:
                            continue
                        lines.append(f"    {sub.name}{'/' if sub.is_dir() else ''}")
                except PermissionError:
                    pass
            else:
                lines.append(f"  {item.name}")
            if len(lines) >= max_entries:
                break
    except Exception:
        pass
    return "\n".join(lines)


def build_code_context(
    workspace_path: str,
    ticket_text: str,
    signals_text: str,
    *,
    max_files: int = 12,
    max_chars: int = 20000,
) -> str:
    root = Path(workspace_path)
    keywords = _pick_keywords(ticket_text + "\n" + signals_text)
    file_hints = _extract_file_hints(signals_text)

    patterns = [
        "*.py", "*.js", "*.ts", "*.tsx", "*.jsx", "*.go", "*.rs", "*.rb",
        "*.java", "*.php", "pyproject.toml", "package.json",
        "requirements.txt", "setup.py", "setup.cfg",
    ]

    seen: set[Path] = set()
    snippets: list[Snippet] = []

    for pat in patterns:
        for p in root.rglob(pat):
            if not p.is_file() or p in seen:
                continue
            if _should_skip(p, root):
                continue
            seen.add(p)
            try:
                if p.stat().st_size > 300_000:
                    continue
                content = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            rel = str(p.relative_to(root))
            lower = content.lower()
            score = sum(lower.count(kw) * 2 for kw in keywords)
            for hint in file_hints:
                if rel.endswith(hint) or hint in rel:
                    score += 30
            if "test" in rel.lower() and any(k in signals_text.lower() for k in ["fail", "error", "assert"]):
                score += 10
            if p.name in {"pyproject.toml", "package.json", "requirements.txt"}:
                score += 5
            if score <= 0:
                continue

            snippets.append(Snippet(
                path=rel,
                score=score,
                excerpt=_best_excerpt(content, keywords),
                language=_detect_language(p),
            ))

    snippets.sort(key=lambda s: s.score, reverse=True)
    snippets = snippets[:max_files]

    parts: list[str] = []
    parts.append(f"**Keywords**: {', '.join(keywords) if keywords else '(none)'}")
    if file_hints:
        parts.append(f"**Files mentioned in failures**: {', '.join(file_hints[:10])}")
    parts.append("")

    tree = _workspace_tree(root)
    if tree:
        parts.append("### Workspace structure")
        parts.append("```")
        parts.append(tree)
        parts.append("```")
        parts.append("")

    used = sum(len(p) for p in parts)
    for snip in snippets:
        lang = snip.language or ""
        block = f"### {snip.path} (score={snip.score})\n```{lang}\n{snip.excerpt}\n```\n"
        if used + len(block) > max_chars:
            short = snip.excerpt[:800] + "\n... (truncated)"
            block = f"### {snip.path} (score={snip.score})\n```{lang}\n{short}\n```\n"
            if used + len(block) > max_chars:
                break
        parts.append(block)
        used += len(block)

    if not snippets:
        return "(no relevant code context found)"

    return "\n".join(parts).strip()[:max_chars]
