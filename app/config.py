"""Application settings (Twelve-Factor III: Config).

Every tunable value comes from environment variables, parsed and validated by
pydantic-settings. A local `.env` file is read *only* as a developer
convenience; in Docker/Kubernetes you inject real env vars and no .env exists.

Why pydantic-settings?
  * typed + validated config (a typo'd PORT fails fast at startup)
  * secrets as `SecretStr`, so they never show up in logs/reprs
  * one object we can inject with FastAPI's dependency system (`get_settings`)
    and override in tests (`app.dependency_overrides[get_settings] = ...`).

Notebook origin: the notebooks did `load_dotenv()` + `os.getenv("OPENAI_API_KEY")`
and built `LiteLlm(model="openai/gpt-4o")` inline (L2 "Intro to ADK"). Neo4j
connection details were read by the course helper `neo4j_for_adk.py`. All of
that is centralised here.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # `.env` is optional; real env vars always win over it.
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Process / HTTP (Factor VII: port binding) -------------------------
    app_name: str = "kg-fastapi-demo"
    environment: Literal["dev", "test", "prod"] = "dev"
    host: str = "0.0.0.0"
    port: int = Field(8000, description="Port the API binds to (PORT env var).")
    log_level: str = "INFO"

    # --- Neo4j: an attached resource (Factor IV) ---------------------------
    # Swap a local container for Aura just by changing NEO4J_URI.
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_username: str = "neo4j"
    neo4j_password: SecretStr = SecretStr("please-change-me")
    neo4j_database: str = "neo4j"

    # --- LLM: also an attached resource ------------------------------------
    # LiteLLM model string, exactly like the notebooks' LiteLlm(model="openai/gpt-4o").
    # Any LiteLLM provider works (e.g. "anthropic/claude-...", "ollama/llama3").
    llm_model: str = "openai/gpt-4o"
    llm_api_base: str | None = None
    openai_api_key: SecretStr | None = None
    # L8 uses neo4j-graphrag's SimpleKGPipeline, which talks to OpenAI directly.
    extraction_model: str = "gpt-4o"
    embedding_model: str = "text-embedding-3-large"

    # --- Files the agents may look at (the notebooks' Neo4j import dir) ----
    # The API reads files from DATA_DIR (sample/search/markdown chunking) and
    # Neo4j reads the *same* files via LOAD CSV "file:///<name>" from its own
    # import dir. docker-compose mounts ./data into both containers.
    data_dir: Path = Path("data")

    # --- State backend (Factor VI: stateless processes) --------------------
    state_backend: Literal["memory", "redis"] = "memory"
    redis_url: str = "redis://localhost:6379/0"
    state_ttl_seconds: int = 60 * 60 * 24  # sessions/jobs expire after a day

    # --- Concurrency (Factor VIII) -----------------------------------------
    # "inprocess": FastAPI BackgroundTasks run the build inside the API process.
    # "worker":    the API enqueues the job in Redis; `python -m app.worker` runs it.
    job_runner: Literal["inprocess", "worker"] = "inprocess"

    # --- Agent knobs borrowed from the notebooks ---------------------------
    schema_loop_max_iterations: int = 2  # L6 LoopAgent(max_iterations=2)
    review_chunk_separator: str = "---"  # L8 RegexTextSplitter("---")
    entity_similarity_threshold: float = 0.1  # L8 jaroWinklerDistance < 0.1

    def openai_key(self) -> str | None:
        return self.openai_api_key.get_secret_value() if self.openai_api_key else None


@lru_cache
def get_settings() -> Settings:
    """Cached settings provider, used as a FastAPI dependency."""
    return Settings()
