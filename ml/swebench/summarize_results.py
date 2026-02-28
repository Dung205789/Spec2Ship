from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    p = argparse.ArgumentParser(description="Summarize SWE-bench harness outputs")
    p.add_argument("--run_id", required=True, help="The run_id you used for swebench.harness.run_evaluation")
    p.add_argument("--results_dir", default="evaluation_results", help="Root folder created by the harness")
    p.add_argument("--out", default="report.md")
    args = p.parse_args()

    run_dir = Path(args.results_dir) / args.run_id
    results_json = run_dir / "results.json"
    instances_jsonl = run_dir / "instance_results.jsonl"

    if not results_json.exists():
        raise SystemExit(f"results.json not found: {results_json}")

    results = json.loads(results_json.read_text(encoding="utf-8"))

    # Instance-level breakdown (optional)
    resolved = 0
    completed = 0
    total = 0
    errors: dict[str, int] = {}

    if instances_jsonl.exists():
        for line in instances_jsonl.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            total += 1
            row = json.loads(line)
            status = str(row.get("status", "")).lower()
            if status in {"resolved", "passed"}:
                resolved += 1
            if status and status not in {"skipped"}:
                completed += 1
            if status in {"error", "failed"}:
                reason = str(row.get("error", row.get("error_msg", "unknown")))[:120]
                errors[reason] = errors.get(reason, 0) + 1

    md = ["# SWE-bench Evaluation Report", ""]
    md.append(f"**Run ID**: `{args.run_id}`")
    md.append(f"**Folder**: `{run_dir}`")
    md.append("")

    # Common top-level keys: the exact schema can change between swebench versions
    md.append("## Summary (results.json)")
    md.append("```json")
    md.append(json.dumps(results, indent=2, ensure_ascii=False)[:6000])
    md.append("```")

    if total:
        md.append("## Instance breakdown")
        md.append(f"- Instances in instance_results.jsonl: {total}")
        md.append(f"- Resolved: {resolved}")
        md.append(f"- Completed (non-skipped): {completed}")
        if errors:
            md.append("\n### Top errors")
            for k, v in sorted(errors.items(), key=lambda kv: kv[1], reverse=True)[:10]:
                md.append(f"- {v}× {k}")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(md) + "\n", encoding="utf-8")

    print(f"Wrote report -> {out_path}")


if __name__ == "__main__":
    main()
