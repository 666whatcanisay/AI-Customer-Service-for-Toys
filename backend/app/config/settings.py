from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv


BACKEND_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BACKEND_ROOT.parent
load_dotenv(BACKEND_ROOT / ".env")


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _resolve_backend_path(value: str | None, default_name: str) -> Path:
    raw = Path(value or default_name).expanduser()
    if not raw.is_absolute():
        raw = BACKEND_ROOT / raw
    return raw.resolve()


def update_env_values(settings: "Settings", values: dict[str, str]) -> None:
    """Persist selected runtime settings without exposing or logging their values."""
    env_path = (settings.backend_root / ".env").resolve()
    backend_root = settings.backend_root.resolve()
    if env_path.parent != backend_root:
        raise ValueError("配置文件路径不在后端目录内")

    normalized: dict[str, str] = {}
    for key, value in values.items():
        if not key.replace("_", "").isalnum() or not key.isupper():
            raise ValueError("环境变量名称不合法")
        if "\r" in value or "\n" in value:
            raise ValueError("配置值不能包含换行符")
        normalized[key] = value

    existing_lines = (
        env_path.read_text(encoding="utf-8").splitlines()
        if env_path.exists()
        else []
    )
    remaining = dict(normalized)
    updated_lines: list[str] = []
    for line in existing_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            updated_lines.append(line)
            continue
        key = line.split("=", 1)[0].strip()
        if key in remaining:
            updated_lines.append(f"{key}={remaining.pop(key)}")
        else:
            updated_lines.append(line)

    if remaining and updated_lines and updated_lines[-1] != "":
        updated_lines.append("")
    updated_lines.extend(f"{key}={value}" for key, value in remaining.items())

    env_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = env_path.with_suffix(".env.tmp")
    temporary_path.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")
    temporary_path.replace(env_path)


@dataclass(frozen=True)
class Settings:
    backend_root: Path
    project_root: Path
    knowledge_base_path: Path
    vector_db_path: Path
    log_dir: Path
    llm_provider: str
    dashscope_api_key: str
    llm_model: str
    llm_base_url: str
    llm_timeout_seconds: float
    llm_temperature: float
    llm_max_tokens: int
    llm_top_p: float
    embedding_model: str
    embedding_offline: bool
    chunk_size: int
    chunk_overlap: int
    chroma_collection_name: str
    test_knowledge_collection_name: str
    platform_api_base_url: str
    platform_api_timeout_seconds: float
    rag_distance_threshold: float
    top_k: int
    host: str
    port: int

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            backend_root=BACKEND_ROOT,
            project_root=PROJECT_ROOT,
            knowledge_base_path=_resolve_backend_path(
                os.getenv("KNOWLEDGE_BASE_PATH"), "knowledge_base"
            ),
            vector_db_path=_resolve_backend_path(
                os.getenv("VECTOR_DB_PATH"), "vector_db"
            ),
            log_dir=_resolve_backend_path(os.getenv("LOG_DIR"), "../logs"),
            llm_provider=os.getenv("LLM_PROVIDER", "ollama").strip(),
            dashscope_api_key=os.getenv("DASHSCOPE_API_KEY", "").strip(),
            llm_model=os.getenv("LLM_MODEL", "qwen3.5:9b").strip(),
            llm_base_url=os.getenv(
                "LLM_BASE_URL", "http://127.0.0.1:11434"
            ).strip().rstrip("/"),
            llm_timeout_seconds=float(os.getenv("LLM_TIMEOUT_SECONDS", "120")),
            llm_temperature=float(os.getenv("LLM_TEMPERATURE", "0.1")),
            llm_max_tokens=max(64, int(os.getenv("LLM_MAX_TOKENS", "512"))),
            llm_top_p=float(os.getenv("LLM_TOP_P", "0.8")),
            embedding_model=os.getenv(
                "EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5"
            ).strip(),
            embedding_offline=_as_bool(os.getenv("EMBEDDING_OFFLINE"), True),
            chunk_size=max(100, int(os.getenv("CHUNK_SIZE", "500"))),
            chunk_overlap=max(0, int(os.getenv("CHUNK_OVERLAP", "100"))),
            chroma_collection_name=os.getenv(
                "CHROMA_COLLECTION_NAME", "documents"
            ).strip(),
            test_knowledge_collection_name=os.getenv(
                "TEST_KNOWLEDGE_COLLECTION_NAME", "test_knowledge_v031"
            ).strip(),
            platform_api_base_url=os.getenv(
                "PLATFORM_API_BASE_URL", ""
            ).strip().rstrip("/"),
            platform_api_timeout_seconds=float(
                os.getenv("PLATFORM_API_TIMEOUT_SECONDS", "30")
            ),
            rag_distance_threshold=float(
                os.getenv(
                    "RAG_DISTANCE_THRESHOLD",
                    os.getenv("DISTANCE_THRESHOLD", "0.6"),
                )
            ),
            top_k=max(1, int(os.getenv("TOP_K", "2"))),
            host=os.getenv("HOST", "127.0.0.1").strip(),
            port=int(os.getenv("PORT", "8000")),
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_env()
