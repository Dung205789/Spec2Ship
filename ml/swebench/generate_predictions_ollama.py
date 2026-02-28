from __future__ import annotations

import argparse
import json
import os
import re
import time
from pathlib import Path
from typing import Any

import httpx
from datasets import load_dataset
from tqdm import tqdm


def ollama_generate(
    *,
    base_url: str,
    model: str,
    prompt: str,
    temperature: float = 0.2,
    num_ctx: int = 8192,
    timeout_s: int = 1800,
) -> str:
    payload: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": temperature, "num_ctx": num_ctx},
    }
    with httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout_s) as client:
        r = client.post("/api/generate", json=payload)
        r.raise_for_status()
        data = r.json()
        return str(data.get("response", ""))


def extract_patch(text: str) -> str:
    t = (text or "").strip()

    # Prefer <patch> wrapper (SWE-bench style)
    if "<patch>" in t and "</patch>" in t:
        m = re.search(r"<patch>\s*(.*?)\s*</patch>", t, flags=re.DOTALL | re.IGNORECASE)
        if m:
            t = m.group(1).strip()

    # Strip markdown fences if present
    t = re.sub(r"^```[a-zA-Z0-9_-]*\n", "", t)
    t = re.sub(r"\n```$", "", t)

    return t.strip()


def main() -> None:
    p = argparse.ArgumentParser(description="Generate SWE-bench predictions using a local Ollama model")
    p.add_argument("--dataset", default="princeton-nlp/SWE-bench_Lite_bm25_13K")
    p.add_argument("--split", default="test")
    p.add_argument("--out", default="predictions.jsonl")
    p.add_argument("--limit", type=int, default=0, help="0 = all")
    p.add_argument("--instance_ids", nargs="*", default=None, help="Optional list of instance_ids")

    p.add_argument("--ollama", default=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"))
    p.add_argument("--model", default=os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b"))
    p.add_argument("--temperature", type=float, default=float(os.getenv("OLLAMA_TEMPERATURE", "0.2")))
    p.add_argument("--num_ctx", type=int, default=int(os.getenv("OLLAMA_NUM_CTX", "8192")))
    p.add_argument("--timeout", type=int, default=int(os.getenv("OLLAMA_TIMEOUT", "1800")))
    p.add_argument("--sleep", type=float, default=0.0, help="Sleep seconds between requests")

    args = p.parse_args()

    ds = load_dataset(args.dataset, split=args.split)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    wanted = set(args.instance_ids) if args.instance_ids else None

    n_written = 0
    with out_path.open("w", encoding="utf-8") as f:
        for row in tqdm(ds, desc="instances"):
            iid = row.get("instance_id")
            if not iid:
                continue
            if wanted is not None and iid not in wanted:
                continue

            prompt = row.get("text")
            if not prompt:
                # fallback: construct a minimal prompt
                prompt = (
                    "You are given a GitHub issue and a repository context. "
                    "Generate a single patch that can be applied with git apply.\n\n"
                    f"ISSUE:\n{row.get('problem_statement', '')}\n"
                )

            raw = ollama_generate(
                base_url=args.ollama,
                model=args.model,
                prompt=prompt,
                temperature=args.temperature,
                num_ctx=args.num_ctx,
                timeout_s=args.timeout,
            )

            patch = extract_patch(raw)
            rec = {
                "instance_id": iid,
                "model_name_or_path": f"ollama:{args.model}",
                "model_patch": patch,
            }
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n_written += 1

            if args.limit and n_written >= args.limit:
                break
            if args.sleep > 0:
                time.sleep(args.sleep)

    print(f"Wrote {n_written} prediction(s) -> {out_path}")


if __name__ == "__main__":
    main()
