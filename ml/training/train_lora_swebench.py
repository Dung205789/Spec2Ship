#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple

def _pick_text_fields(ex: Dict[str, Any]) -> Tuple[str, str]:
    """
    Best-effort extraction of (prompt, completion) from SWE-bench-style datasets.

    Supported patterns:
    - ex has 'text' containing prompt with <patch>...</patch> OR prompt only + ex['patch']
    - ex has 'problem_statement' + 'patch'
    - fall back to stringify
    """
    text = ex.get("text")
    patch = ex.get("patch") or ex.get("model_patch") or ex.get("diff") or ""
    if isinstance(text, str) and text.strip():
        # If the text already contains a <patch> block, split on it.
        low = text.lower()
        start = low.find("<patch>")
        end = low.find("</patch>")
        if start != -1 and end != -1 and end > start:
            prompt = text[:start].rstrip() + "\n\n<patch>\n"
            completion = text[start + len("<patch>"):end].strip() + "\n</patch>\n"
            return prompt, completion
        # Otherwise, use text as prompt and patch as completion
        prompt = text.rstrip() + "\n\n<patch>\n"
        completion = str(patch).strip() + "\n</patch>\n"
        return prompt, completion

    ps = ex.get("problem_statement") or ex.get("issue_text") or ex.get("instruction") or ""
    if isinstance(ps, str) and ps.strip():
        prompt = (
            "You are a senior software engineer.\n"
            "Given the following issue, output a valid unified diff that fixes it.\n\n"
            f"Issue:\n{ps.strip()}\n\n"
            "<patch>\n"
        )
        completion = str(patch).strip() + "\n</patch>\n"
        return prompt, completion

    # Worst case: dump record
    prompt = "Produce a valid unified diff patch.\n\n<patch>\n"
    completion = json.dumps(ex, ensure_ascii=False)[:2000] + "\n</patch>\n"
    return prompt, completion


@dataclass
class EncodedExample:
    input_ids: List[int]
    attention_mask: List[int]
    labels: List[int]


def main() -> int:
    ap = argparse.ArgumentParser(description="LoRA SFT for SWE-bench patch generation (CPU-friendly defaults).")
    ap.add_argument("--base_model", required=True, help="HF model id, e.g. Qwen/Qwen2.5-Coder-0.5B-Instruct")
    ap.add_argument("--dataset", required=True, help="HF dataset id, e.g. princeton-nlp/SWE-bench_bm25_13K")
    ap.add_argument("--split", default="train")
    ap.add_argument("--limit", type=int, default=0, help="limit number of training rows (0 = full split)")
    ap.add_argument("--output_dir", required=True, help="where to write LoRA adapter")
    ap.add_argument("--max_steps", type=int, default=100)
    ap.add_argument("--learning_rate", type=float, default=2e-4)
    ap.add_argument("--batch_size", type=int, default=1)
    ap.add_argument("--grad_accum", type=int, default=8)
    ap.add_argument("--max_seq_len", type=int, default=2048)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--device", default="cpu", choices=["cpu", "cuda"], help="cuda requires a GPU-enabled environment")
    args = ap.parse_args()

    from datasets import load_dataset
    import torch
    from transformers import (
        AutoModelForCausalLM,
        AutoTokenizer,
        Trainer,
        TrainingArguments,
    )
    from peft import LoraConfig, get_peft_model

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    # Load data
    ds = load_dataset(args.dataset, split=args.split)
    if args.limit and args.limit > 0:
        ds = ds.select(range(min(args.limit, len(ds))))

    # Tokenizer / model
    tok = AutoTokenizer.from_pretrained(args.base_model, use_fast=True)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token

    torch_dtype = torch.float16 if (args.device == "cuda") else torch.float32
    model = AutoModelForCausalLM.from_pretrained(
        args.base_model,
        torch_dtype=torch_dtype,
        device_map="auto" if args.device == "cuda" else None,
    )

    # LoRA config (works for most decoder-only code models)
    target_modules = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]
    lora = LoraConfig(
        r=16,
        lora_alpha=32,
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=target_modules,
    )
    model = get_peft_model(model, lora)
    model.print_trainable_parameters()

    def encode(ex: Dict[str, Any]) -> EncodedExample:
        prompt, completion = _pick_text_fields(ex)
        full = prompt + completion
        prompt_ids = tok(prompt, truncation=True, max_length=args.max_seq_len, add_special_tokens=False)["input_ids"]
        full_enc = tok(full, truncation=True, max_length=args.max_seq_len, add_special_tokens=False)
        input_ids = full_enc["input_ids"]
        attn = full_enc["attention_mask"]
        labels = input_ids.copy()
        # Mask prompt tokens so loss is only on completion
        pl = min(len(prompt_ids), len(labels))
        for i in range(pl):
            labels[i] = -100
        return EncodedExample(input_ids=input_ids, attention_mask=attn, labels=labels)

    # Pre-encode for speed & deterministic masking
    encoded: List[EncodedExample] = []
    for ex in ds:
        encoded.append(encode(ex))

    class _TorchDataset(torch.utils.data.Dataset):
        def __len__(self):
            return len(encoded)
        def __getitem__(self, idx: int):
            e = encoded[idx]
            return {
                "input_ids": torch.tensor(e.input_ids, dtype=torch.long),
                "attention_mask": torch.tensor(e.attention_mask, dtype=torch.long),
                "labels": torch.tensor(e.labels, dtype=torch.long),
            }

    def collate(batch):
        import torch
        # pad to max len in batch
        maxlen = max(x["input_ids"].shape[0] for x in batch)
        def pad1(t, pad_val):
            pad_len = maxlen - t.shape[0]
            if pad_len <= 0:
                return t
            return torch.cat([t, torch.full((pad_len,), pad_val, dtype=t.dtype)], dim=0)
        input_ids = torch.stack([pad1(x["input_ids"], tok.pad_token_id) for x in batch])
        attention_mask = torch.stack([pad1(x["attention_mask"], 0) for x in batch])
        labels = torch.stack([pad1(x["labels"], -100) for x in batch])
        return {"input_ids": input_ids, "attention_mask": attention_mask, "labels": labels}

    train_args = TrainingArguments(
        output_dir=str(out / "trainer_out"),
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        max_steps=args.max_steps,
        learning_rate=args.learning_rate,
        logging_steps=10,
        save_steps=max(50, args.max_steps // 2),
        save_total_limit=2,
        bf16=False,
        fp16=(args.device == "cuda"),
        report_to=[],
        seed=args.seed,
        dataloader_num_workers=0,
        remove_unused_columns=False,
    )

    trainer = Trainer(
        model=model,
        args=train_args,
        train_dataset=_TorchDataset(),
        data_collator=collate,
    )

    trainer.train()

    # Save adapter + tokenizer
    model.save_pretrained(str(out))
    tok.save_pretrained(str(out))

    meta = {
        "base_model": args.base_model,
        "dataset": args.dataset,
        "split": args.split,
        "limit": args.limit,
        "max_steps": args.max_steps,
        "learning_rate": args.learning_rate,
        "batch_size": args.batch_size,
        "grad_accum": args.grad_accum,
        "max_seq_len": args.max_seq_len,
    }
    (out / "train_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    print("OK: wrote LoRA adapter to", str(out))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
