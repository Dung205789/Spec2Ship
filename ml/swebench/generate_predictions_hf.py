#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict

def _extract_patch(text: str) -> str:
    if not text:
        return ""
    low = text.lower()
    s = low.find("<patch>")
    e = low.find("</patch>")
    if s != -1 and e != -1 and e > s:
        return text[s + len("<patch>"):e].strip()
    # try fenced diff
    m = re.search(r"```diff\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return text.strip()

def main() -> int:
    ap = argparse.ArgumentParser(description="Generate SWE-bench predictions using a local HF model (optionally with LoRA adapter).")
    ap.add_argument("--dataset", required=True, help="HF dataset id providing prompt 'text' and 'instance_id'")
    ap.add_argument("--split", default="test")
    ap.add_argument("--out", required=True, help="output predictions.jsonl")
    ap.add_argument("--base_model", required=True, help="HF base model id")
    ap.add_argument("--adapter", default="", help="path to LoRA adapter dir (optional)")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--max_new_tokens", type=int, default=512)
    ap.add_argument("--temperature", type=float, default=0.2)
    ap.add_argument("--top_p", type=float, default=0.95)
    ap.add_argument("--device", default="cpu", choices=["cpu", "cuda"])
    args = ap.parse_args()

    from datasets import load_dataset
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import PeftModel

    ds = load_dataset(args.dataset, split=args.split)
    if args.limit and args.limit > 0:
        ds = ds.select(range(min(args.limit, len(ds))))

    tok = AutoTokenizer.from_pretrained(args.base_model, use_fast=True)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token

    torch_dtype = torch.float16 if (args.device == "cuda") else torch.float32
    model = AutoModelForCausalLM.from_pretrained(
        args.base_model,
        torch_dtype=torch_dtype,
        device_map="auto" if args.device == "cuda" else None,
    )

    if args.adapter:
        model = PeftModel.from_pretrained(model, args.adapter)

    model.eval()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with out_path.open("w", encoding="utf-8") as f:
        for ex in ds:
            instance_id = ex.get("instance_id") or ex.get("id") or ex.get("problem_id") or ""
            prompt = ex.get("text") or ex.get("prompt") or ex.get("problem_statement") or ""
            if not isinstance(prompt, str):
                prompt = str(prompt)

            # Encourage patch-only output
            prompt2 = prompt.rstrip() + "\n\n<patch>\n"
            inputs = tok(prompt2, return_tensors="pt", truncation=True, max_length=4096)
            if args.device == "cuda":
                inputs = {k: v.to(model.device) for k, v in inputs.items()}

            with torch.no_grad():
                gen = model.generate(
                    **inputs,
                    max_new_tokens=args.max_new_tokens,
                    do_sample=(args.temperature > 0),
                    temperature=max(args.temperature, 1e-5),
                    top_p=args.top_p,
                    pad_token_id=tok.pad_token_id,
                    eos_token_id=tok.eos_token_id,
                )

            decoded = tok.decode(gen[0], skip_special_tokens=True)
            # take completion portion after prompt2
            completion = decoded[len(prompt2):] if decoded.startswith(prompt2) else decoded
            patch = _extract_patch(completion)

            rec: Dict[str, Any] = {
                "instance_id": instance_id,
                "model_name_or_path": args.base_model + (f"+lora({args.adapter})" if args.adapter else ""),
                "model_patch": patch,
            }
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print("OK: wrote", str(out_path))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
