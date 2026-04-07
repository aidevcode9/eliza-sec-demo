"""Configuration — all thresholds and settings in one place."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root (or src/.env as fallback)
_project_root = Path(__file__).resolve().parent.parent
for _env_path in [_project_root / ".env", _project_root / "src" / ".env"]:
    if _env_path.exists():
        load_dotenv(_env_path)
        break


@dataclass
class Config:
    """Assignment configuration. Tune thresholds here, not in code."""

    # --- LLM ---
    llm_provider: str = os.getenv("LLM_PROVIDER", "openai")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    model_id: str = os.getenv("MODEL_ID", "gpt-5.4-mini")
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "text-embedding-3-large")
    embedding_dimensions: int = int(os.getenv("EMBEDDING_DIMENSIONS", "1536"))

    # --- Retrieval ---
    top_k: int = int(os.getenv("TOP_K", "5"))
    # NOTE: Do NOT hard-filter on RRF fusion scores. They are not comparable to cosine similarity.
    # Return top-k results and let the generation prompt handle uncertainty.
    # Only enable threshold if empirical testing proves noise in top-k results.
    confidence_threshold: float = float(os.getenv("CONFIDENCE_THRESHOLD", "0.0"))
    chunk_size: int = int(os.getenv("CHUNK_SIZE", "2000"))
    chunk_overlap: int = int(os.getenv("CHUNK_OVERLAP", "200"))

    # --- Citation validation ---
    jaccard_threshold: float = float(os.getenv("JACCARD_THRESHOLD", "0.30"))

    # --- Paths ---
    data_dir: str = os.getenv("DATA_DIR", "data")
    vector_store_path: str = os.getenv("VECTOR_STORE_PATH", "vector_store")

    # --- Telemetry ---
    telemetry_enabled: bool = os.getenv("TELEMETRY_ENABLED", "true").lower() == "true"
    log_level: str = os.getenv("LOG_LEVEL", "INFO")

    # --- Langfuse ---
    langfuse_secret_key: str = os.getenv("LANGFUSE_SECRET_KEY", "")
    langfuse_public_key: str = os.getenv("LANGFUSE_PUBLIC_KEY", "")
    langfuse_host: str = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")


config = Config()
