import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class ModelEndpoint:
    name: str
    base_url: str
    model: str
    api_key: str = field(repr=False)


@dataclass(frozen=True)
class Settings:
    mode: str = "mock"
    max_retries: int = 2
    llm_providers: tuple[ModelEndpoint, ...] = ()
    llm_timeout_seconds: float = 60
    local_llm_timeout_seconds: float = 15
    task_timeout_seconds: float = 240
    max_model_concurrency: int = 2
    circuit_cooldown_seconds: float = 30
    # 按 phase 设定的 token 上限，避免 extract 这类小输出被分配 4096 的冗余预算。
    extract_max_tokens: int = 1024
    explain_max_tokens: int = 2048
    # Web 桥接层容量参数，避免在源码里散落 magic number。
    web_request_max_bytes: int = 131072
    web_queue_capacity: int = 16
    web_worker_threads: int = 2
    web_session_max_age: int = 28800
    web_task_list_limit: int = 100

    def __post_init__(self):
        if self.mode not in {"mock", "real"}:
            raise ValueError("HYSYS_MODE 必须是 mock 或 real")
        if not 0 <= self.max_retries <= 2:
            raise ValueError("MAX_RETRIES 必须为 0～2")
        if not 0 < self.llm_timeout_seconds <= 180:
            raise ValueError("LLM_TIMEOUT_SECONDS 必须为 0～180 秒")
        if not 0 < self.local_llm_timeout_seconds <= 180:
            raise ValueError("LOCAL_LLM_TIMEOUT_SECONDS 必须为 0～180 秒")
        if not 1 <= self.task_timeout_seconds <= 3600:
            raise ValueError("TASK_TIMEOUT_SECONDS 必须为1～3600秒")
        if not 1 <= self.max_model_concurrency <= 32:
            raise ValueError("MAX_MODEL_CONCURRENCY 必须为1～32")
        if not 1 <= self.circuit_cooldown_seconds <= 900:
            raise ValueError("CIRCUIT_COOLDOWN_SECONDS 必须为1～900秒")

    @classmethod
    def from_env(cls):
        env_file = Path(os.getenv("HYSYS_ENV_FILE", ".env"))
        if not env_file.is_file() and "HYSYS_ENV_FILE" not in os.environ:
            env_file = Path(__file__).resolve().parents[1] / ".env"
        load_dotenv(env_file, override=False)
        endpoints = tuple(
            ModelEndpoint(
                name,
                os.getenv(prefix + "_BASE_URL", ""),
                os.getenv(prefix + "_MODEL", ""),
                os.getenv(prefix + "_API_KEY", ""),
            )
            for name, prefix in [
                ("local", "LOCAL"),
                ("deepseek", "DEEPSEEK"),
                ("siliconflow", "SILICONFLOW"),
            ]
        )
        return cls(
            os.getenv("HYSYS_MODE", "mock"),
            int(os.getenv("MAX_RETRIES", "2")),
            llm_providers=endpoints,
            llm_timeout_seconds=float(os.getenv("LLM_TIMEOUT_SECONDS", "60")),
            local_llm_timeout_seconds=float(os.getenv("LOCAL_LLM_TIMEOUT_SECONDS", "15")),
            task_timeout_seconds=float(os.getenv("TASK_TIMEOUT_SECONDS", "240")),
            max_model_concurrency=int(os.getenv("MAX_MODEL_CONCURRENCY", "2")),
            circuit_cooldown_seconds=float(os.getenv("CIRCUIT_COOLDOWN_SECONDS", "30")),
            extract_max_tokens=int(os.getenv("EXTRACT_MAX_TOKENS", "1024")),
            explain_max_tokens=int(os.getenv("EXPLAIN_MAX_TOKENS", "2048")),
            web_request_max_bytes=int(os.getenv("HYSYS_WEB_REQUEST_MAX_BYTES", "131072")),
            web_queue_capacity=int(os.getenv("HYSYS_WEB_QUEUE_CAPACITY", "16")),
            web_worker_threads=int(os.getenv("HYSYS_WEB_WORKER_THREADS", "2")),
            web_session_max_age=int(os.getenv("HYSYS_WEB_SESSION_MAX_AGE", "28800")),
            web_task_list_limit=int(os.getenv("HYSYS_WEB_TASK_LIST_LIMIT", "100")),
        )
