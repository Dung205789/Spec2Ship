#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   bash ml/swebench/run_evaluation.sh <RUN_ID> <PREDICTIONS_JSONL>
#
# This invokes the SWE-bench harness (Docker-based). It will build/cache images and can
# consume a lot of disk. Start small (Lite + a few instance_ids).

RUN_ID=${1:?run_id required}
PRED=${2:?predictions.jsonl required}

python -m swebench.harness.run_evaluation \
  --dataset_name princeton-nlp/SWE-bench_Lite \
  --predictions_path "${PRED}" \
  --max_workers 4 \
  --run_id "${RUN_ID}"
