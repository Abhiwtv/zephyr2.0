import os
from typing import Optional
from pathlib import Path
from pydantic import BaseModel, Field

# Try loading .env if python-dotenv is available
try:
    from dotenv import load_dotenv
    # Find repository root (parent of 'core' directory)
    _REPO_ROOT = Path(__file__).resolve().parent.parent
    _ENV_FILE = _REPO_ROOT / ".env"
    if _ENV_FILE.exists():
        load_dotenv(dotenv_path=_ENV_FILE)
    else:
        load_dotenv()
except ImportError:
    _REPO_ROOT = Path(__file__).resolve().parent.parent

_REPO_ROOT_STR = str(Path(__file__).resolve().parent.parent)

class Settings(BaseModel):
    """
    Centralized configuration settings for Zephyr 2.0 / NetCoop AI.
    Loads values from environment variables or .env file with sane defaults.
    """
    # Remote LLM & Inference Engine Settings
    ENGINE_URL: Optional[str] = Field(
        default_factory=lambda: (
            (os.getenv("ENGINE_URL") or os.getenv("OLLAMA_BASE_URL") or "").rstrip("/") or None
        ),
        description="Base URL for Ollama/vLLM inference (Cloudflare tunnel or local)"
    )
    OLLAMA_MODEL: str = Field(
        default_factory=lambda: os.getenv("OLLAMA_MODEL", "qwen3:14b"),
        description="Target model identifier (e.g. qwen3:14b, qwen2.5:14b)"
    )
    REASONER_TIMEOUT_SECONDS: int = Field(
        default_factory=lambda: int(os.getenv("REASONER_TIMEOUT_SECONDS", "90")),
        description="Inference timeout in seconds for Brain Reasoner"
    )
    VOTER_TIMEOUT_SECONDS: int = Field(
        default_factory=lambda: int(os.getenv("VOTER_TIMEOUT_SECONDS", "30")),
        description="Inference timeout in seconds for Domain Voters"
    )

    # Server & API Settings
    HOST: str = Field(
        default_factory=lambda: os.getenv("HOST", "0.0.0.0"),
        description="API binding host"
    )
    PORT: int = Field(
        default_factory=lambda: int(os.getenv("PORT", "8000")),
        description="API binding port"
    )
    DEBUG: bool = Field(
        default_factory=lambda: os.getenv("DEBUG", "false").lower() in ("true", "1", "yes"),
        description="Debug mode enable/disable"
    )

    # Cloud & Deployment Controls
    KAGGLE_USER: Optional[str] = Field(
        default_factory=lambda: os.getenv("KAGGLE_USER") or os.getenv("KAGGLE_USERNAME"),
        description="Kaggle username for headless GPU runner"
    )
    KAGGLE_KEY: Optional[str] = Field(
        default_factory=lambda: os.getenv("KAGGLE_KEY"),
        description="Kaggle API key"
    )
    ORACLE_HOST: Optional[str] = Field(
        default_factory=lambda: os.getenv("ORACLE_HOST"),
        description="Oracle VM public IP or hostname"
    )

    # Data & Storage Paths
    REPO_ROOT: str = Field(
        default=_REPO_ROOT_STR,
        description="Absolute path to the repository root directory"
    )
    DATA_DIR: str = Field(
        default_factory=lambda: os.getenv(
            "DATA_DIR",
            os.path.join(_REPO_ROOT_STR, "data")
        ),
        description="Directory for persistent data stores and benchmark datasets"
    )
    INCIDENT_MEMORY_PATH: str = Field(
        default_factory=lambda: os.getenv(
            "INCIDENT_MEMORY_PATH",
            os.path.join(_REPO_ROOT_STR, "data", "incident_memory.json")
        ),
        description="Persistent path to incident memory JSON"
    )
    BENCHMARK_DATASET_PATH: str = Field(
        default_factory=lambda: os.getenv(
            "BENCHMARK_DATASET_PATH",
            os.path.join(_REPO_ROOT_STR, "data", "benchmark_dataset.jsonl")
        ),
        description="Ground truth benchmark dataset file path"
    )
    EVALUATION_RESULTS_PATH: str = Field(
        default_factory=lambda: os.getenv(
            "EVALUATION_RESULTS_PATH",
            os.path.join(_REPO_ROOT_STR, "data", "evaluation_results.jsonl")
        ),
        description="Audit output log for benchmark results"
    )
    OUTPUT_JSON_PATH: str = Field(
        default_factory=lambda: os.getenv(
            "OUTPUT_JSON_PATH",
            os.path.join(_REPO_ROOT_STR, "output.json")
        ),
        description="Live incident report output JSON path"
    )

    # Multi-Agent Consensus Parameters
    CONSENSUS_THRESHOLD: float = Field(
        default_factory=lambda: float(os.getenv("CONSENSUS_THRESHOLD", "0.70")),
        description="Minimum weighted confidence required to exit debate"
    )
    MAX_DEBATE_ROUNDS: int = Field(
        default_factory=lambda: int(os.getenv("MAX_DEBATE_ROUNDS", "3")),
        description="Maximum debate epochs before forcing best available diagnosis"
    )

    @property
    def OLLAMA_BASE_URL(self) -> str:
        """Alias property for ENGINE_URL to maintain backwards compatibility."""
        return self.ENGINE_URL

# Global state to track the active GPU tunnel URL
class EngineState:
    url: Optional[str] = os.environ.get("ENGINE_URL", None) or None

    @classmethod
    def get_url(cls) -> Optional[str]:
        return cls.url or os.environ.get("ENGINE_URL", None) or None

    @classmethod
    def get_chat_url(cls) -> str:
        base = cls.get_url().rstrip("/")
        if base.endswith("/v1/chat/completions"):
            return base
        if base.endswith("/api/generate"):
            base = base.replace("/api/generate", "")
        return f"{base}/v1/chat/completions"

# Singleton instance
settings = Settings()
EngineState.url = settings.ENGINE_URL
