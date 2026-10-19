import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None


class Settings:
    def __init__(self) -> None:
        self.backend_dir = Path(__file__).resolve().parents[2]
        if load_dotenv:
            load_dotenv(self.backend_dir / ".env")
        self.app_name = os.getenv("APP_NAME", "KnowLoop")
        self.app_env = os.getenv("APP_ENV", "development")
        self.backend_host = os.getenv("BACKEND_HOST", "0.0.0.0")
        self.backend_port = int(os.getenv("BACKEND_PORT", "8000"))
        self.data_dir = self._resolve_path(os.getenv("DATA_DIR", "./data"))
        self.storage_dir = self._resolve_path(os.getenv("STORAGE_DIR", "./storage/original"))
        self.max_upload_mb = int(os.getenv("MAX_UPLOAD_MB", "30"))
        self.default_chunk_size = int(os.getenv("DEFAULT_CHUNK_SIZE", "1200"))
        self.default_overlap = int(os.getenv("DEFAULT_OVERLAP", "100"))
        self.default_top_k = int(os.getenv("DEFAULT_TOP_K", "5"))
        self.default_score_threshold = float(os.getenv("DEFAULT_SCORE_THRESHOLD", "0.2"))
        self.full_scan_max_chunks = int(os.getenv("FULL_SCAN_MAX_CHUNKS", "200"))
        self.embedding_provider = os.getenv("EMBEDDING_PROVIDER", "openai-compatible")
        self.embedding_base_url = os.getenv("EMBEDDING_BASE_URL", "https://api.example.com/v1")
        self.embedding_api_key = os.getenv("EMBEDDING_API_KEY", "")
        self.embedding_model = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
        self.embedding_mock = os.getenv("EMBEDDING_MOCK", "true").lower() == "true"
        self.embedding_dim = int(os.getenv("EMBEDDING_DIM", "384"))
        self.llm_provider = os.getenv("LLM_PROVIDER", "openai-compatible")
        self.llm_base_url = os.getenv("LLM_BASE_URL", "https://api.example.com/v1")
        self.llm_api_key = os.getenv("LLM_API_KEY", "")
        self.llm_model = os.getenv("LLM_MODEL", "gpt-4o-mini")
        self.llm_mock = os.getenv("LLM_MOCK", "true").lower() == "true"
        self.chat_runtime = os.getenv("CHAT_RUNTIME", "langgraph").strip().lower()
        if self.chat_runtime not in {"legacy", "langgraph"}:
            raise ValueError("CHAT_RUNTIME must be legacy or langgraph")
        self.agent_max_rounds = min(3, max(1, int(os.getenv("AGENT_MAX_RETRIEVAL_ROUNDS", "3"))))
        self.agent_max_seconds = max(1, float(os.getenv("AGENT_MAX_SECONDS", "180")))
        self.agent_max_llm_calls = max(1, int(os.getenv("AGENT_MAX_LLM_CALLS", "8")))
        self.agent_max_tool_calls = max(1, int(os.getenv("AGENT_MAX_TOOL_CALLS", "8")))
        self.evidence_review_enabled = os.getenv("EVIDENCE_REVIEW_ENABLED", "true").strip().lower() == "true"
        self.evidence_review_max_revisions = int(os.getenv("EVIDENCE_REVIEW_MAX_REVISIONS", "1"))
        if self.evidence_review_max_revisions not in {0, 1}:
            raise ValueError("EVIDENCE_REVIEW_MAX_REVISIONS must be 0 or 1")

    def _resolve_path(self, value: str) -> Path:
        path = Path(value)
        if path.is_absolute():
            return path
        return self.backend_dir / path


settings = Settings()
