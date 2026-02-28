from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str = "postgresql+psycopg2://spec2ship:spec2ship@localhost:5432/spec2ship"
    redis_url: str = "redis://localhost:6379/0"

    workspace_path: str = "/workspace/sample_workspace"
    workspaces_root: str = "/workspace/workspaces"
    artifacts_dir: str = "/data/artifacts"

    # Workspace isolation
    isolate_workspaces: bool = True
    run_workspaces_dir: str = "/data/run_workspaces"

    # Upload limits
    workspace_upload_max_bytes: int = 200 * 1024 * 1024
    workspace_extract_max_bytes: int = 800 * 1024 * 1024
    workspace_extract_max_files: int = 20000
    workspace_extract_max_file_bytes: int = 50 * 1024 * 1024

    # Timeouts — LOW defaults for local/slow machines
    # For a fast server: preflight=30, smoke=120, apply=180, test=1800, max=900
    preflight_seconds: int = 30
    smoke_seconds: int = 60
    apply_patch_seconds: int = 120
    max_command_seconds: int = 300      # low for local; server: 900
    git_command_seconds: int = 120      # server: 600
    test_command_seconds: int = 300     # server: 1800

    # Patch proposer: "rules" | "ollama" | "hf"
    patcher_mode: str = "rules"

    # Patch robustness
    patch_max_attempts: int = 2
    max_patch_iterations: int = 2

    # Ollama
    ollama_base_url: str = "http://ollama:11434"
    ollama_model: str = "qwen2.5-coder:7b"
    ollama_timeout_seconds: int = 300   # low for local; server: 600+
    ollama_temperature: float = 0.15
    ollama_num_ctx: int = 4096          # low for local; server: 8192+

    # HuggingFace local patcher
    hf_model: str = "Qwen/Qwen2.5-Coder-0.5B-Instruct"
    hf_adapter_path: str = ""
    hf_device: str = "cpu"
    hf_max_new_tokens: int = 512        # low for local; server: 800+
    hf_temperature: float = 0.2
    hf_top_p: float = 0.95

    # Code context for LLM prompts
    code_context_max_files: int = 8     # server: 12-15
    code_context_max_chars: int = 12000 # server: 20000+

    # RQ job
    rq_job_timeout_seconds: int = 7200
    approval_wait_seconds: int = 600

    # ML scripts dir
    ml_dir: str = "/ml"

    # SWE-bench defaults — LOW for flow testing
    swebench_prompt_dataset: str = "princeton-nlp/SWE-bench_Lite_bm25_13K"
    swebench_dataset_name: str = "princeton-nlp/SWE-bench_Lite"
    swebench_max_workers: int = 1


settings = Settings()
