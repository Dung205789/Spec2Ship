# ML / AI Integration

Spec2Ship supports three AI modes for patch generation, plus a benchmark evaluation workflow.

## Patcher modes

| Mode | Description | Requirements |
|------|-------------|--------------|
| `rules` | Deterministic rule-based (default) | None — works offline |
| `ollama` | LLM via Ollama (best results) | `docker-compose.llm.yml` |
| `hf` | Local HuggingFace model + optional LoRA | `docker-compose.train.yml` |

## Quick: enable Ollama patcher

```bash
docker compose -f docker-compose.yml -f docker-compose.llm.yml up -d --build
docker compose -f docker-compose.yml -f docker-compose.llm.yml exec ollama ollama pull qwen2.5-coder:7b
```

Then set `PATCHER_MODE=ollama` in `.env`.

## Benchmark: SWE-bench evaluation

Run the SWE-bench preset from the UI.  
Default config (flow check, slow machines): `limit=2`, `max_workers=1`.

For real evaluation on a server:
- Set `limit=50` to `300` (SWE-bench Lite has 300 issues)
- Set `max_workers=4` or higher

## Training: LoRA fine-tuning

Use the "Train LoRA + Eval" preset from the UI.  
Default config (flow check): `train_limit=50`, `max_steps=20`.

For meaningful training on a server:
- `train_limit=2000`, `max_steps=200`, `device=cuda`

## Performance tuning by machine

### Local / slow (default — flow testing)
```
OLLAMA_NUM_CTX=4096
OLLAMA_TIMEOUT_SECONDS=300
HF_MAX_NEW_TOKENS=512
TEST_COMMAND_SECONDS=300
train_limit=50, max_steps=20
swebench limit=2
```

### Server (production quality)
```
OLLAMA_NUM_CTX=8192
OLLAMA_TIMEOUT_SECONDS=900
HF_MAX_NEW_TOKENS=1000
HF_DEVICE=cuda
TEST_COMMAND_SECONDS=1800
CODE_CONTEXT_MAX_FILES=15
CODE_CONTEXT_MAX_CHARS=24000
train_limit=2000, max_steps=200
swebench limit=100-300, max_workers=4
```
