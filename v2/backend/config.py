import os
from pathlib import Path
from dotenv import load_dotenv

WORKSPACE_ROOT = Path(__file__).parent.parent
load_dotenv(WORKSPACE_ROOT / ".env")

MODEL_TIERS = {
    "strategic": [
        {"provider": "groq", "reasoning_type": "advanced", "is_preferred": True, "is_free": True},
        {"provider": "nvidia_nim", "reasoning_type": "advanced", "is_preferred": True, "is_free": True},
        {"provider": "openrouter", "reasoning_type": "advanced", "is_preferred": False, "is_free": True},
        {"provider": "sambanova", "reasoning_type": "advanced", "is_backup": True},
        {"provider": "opencode", "reasoning_type": "advanced", "is_backup": True},
        {"provider": "cohere", "reasoning_type": "advanced", "is_backup": True},
        {"provider": "cerebras", "reasoning_type": "advanced", "is_backup": True}
    ],
    "coding": [
        {"provider": "groq", "reasoning_type": "logical", "is_preferred": True, "is_free": True},
        {"provider": "nvidia_nim", "reasoning_type": "logical", "is_preferred": True, "is_free": True},
        {"provider": "openrouter", "reasoning_type": "logical", "is_preferred": False, "is_free": True},
        {"provider": "sambanova", "reasoning_type": "logical", "is_backup": True},
        {"provider": "opencode", "reasoning_type": "logical", "is_backup": True},
        {"provider": "cohere", "reasoning_type": "logical", "is_backup": True},
        {"provider": "cerebras", "reasoning_type": "logical", "is_backup": True}
    ],
    "fast_eval": [
        {"provider": "groq", "reasoning_type": "fast", "is_preferred": True, "is_free": True},
        {"provider": "nvidia_nim", "reasoning_type": "fast", "is_preferred": True, "is_free": True},
        {"provider": "openrouter", "reasoning_type": "fast", "is_preferred": False, "is_free": True},
        {"provider": "sambanova", "reasoning_type": "fast", "is_backup": True},
        {"provider": "opencode", "reasoning_type": "fast", "is_backup": True},
        {"provider": "cohere", "reasoning_type": "fast", "is_backup": True},
        {"provider": "cerebras", "reasoning_type": "fast", "is_backup": True}
    ]
}

EVAL_REPORTS_DIR = WORKSPACE_ROOT / "eval" / "reports"
PROVIDER_TIMEOUT_SECONDS = 25
PROVIDER_CALL_TIMEOUT_SECONDS = 20
MODEL_REFRESH_TTL_SECONDS = int(os.getenv("MODEL_REFRESH_TTL_SECONDS", "3600"))
PROVIDER_HEALTH_COOLDOWN_SECONDS = int(os.getenv("PROVIDER_HEALTH_COOLDOWN_SECONDS", "300"))

# Ordered fallback chain (derived from the strategic tier) — legacy e2e API.
LLM_CHAIN = [spec["provider"] for spec in MODEL_TIERS["strategic"]]

# Restored Original Variables
RECOVERY_BUDGET_PER_SUBTASK = int(os.getenv("RECOVERY_BUDGET_PER_SUBTASK", "3"))
MAX_AGENT_STEPS = int(os.getenv("MAX_AGENT_STEPS", "25"))
TOOL_TIMEOUT_SECONDS = int(os.getenv("TOOL_TIMEOUT_SECONDS", "30"))
HEVA_E2E = os.getenv("HEVA_E2E", "0") == "1"
NVIDIA_NIM_BASE_URL = os.getenv("NVIDIA_NIM_BASE_URL", "https://integrate.api.nvidia.com/v1")

# API Keys
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
COHERE_API_KEY = os.getenv("COHERE_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
CEREBRAS_API_KEY = os.getenv("CEREBRAS_API_KEY", "")
SAMBANOVA_API_KEY = os.getenv("SAMBANOVA_API_KEY", "")
NVIDIA_NIM_API_KEY = os.getenv("NVIDIA_NIM_API_KEY", "")
OPEN_CODE_API_KEY = os.getenv("OPEN_CODE_API_KEY", "")
OPEN_CODE_BASE_URL = os.getenv("OPEN_CODE_BASE_URL", "https://opencode.ai/inference/openai/v1")

# Turso (libSQL) Remote Storage (optional — falls back to local SQLite/FAISS)
TURSO_DATABASE_URL = os.getenv("TURSO_DATABASE_URL", "")
TURSO_AUTH_TOKEN = os.getenv("TURSO_AUTH_TOKEN", "")
