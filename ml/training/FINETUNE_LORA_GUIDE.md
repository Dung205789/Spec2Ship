# LoRA fine-tuning guide (optional)

This is an *optional* step after you have a baseline evaluation score.

## Why you might fine-tune

Fine-tuning can help when:
- Your model repeatedly makes the *same kind of mistake* (format, patch style, missing imports).
- Your domain is specific (internal monorepo conventions, company frameworks).
- You have enough training data (hundreds–thousands of issue→patch examples).

For general Python OSS bug-fixing, strong base code models + good prompting usually beat naïve fine-tunes.

## Practical plan (Kaggle / single GPU)

1) Start from a code model that supports LoRA well (Qwen2.5-Coder-7B is a common choice).
2) Build an SFT dataset:
   - input: (issue statement + retrieved context + tool signals)
   - output: unified diff patch
3) Train LoRA with PEFT + bitsandbytes (4-bit) if needed.
4) Export LoRA + base model.
5) Evaluate again on SWE-bench Lite.

## Data format suggestion

Use JSONL with fields:

```json
{"instruction": "Fix the issue...", "input": "<repo context + failing tests>", "output": "diff --git ..."}
```

## What to watch

- **Overfitting**: score goes up on a small subset but down on new instances.
- **Patch format drift**: always enforce `git apply` compatible patches.
- **Compute cost**: a better base model might be cheaper than a fine-tune.
