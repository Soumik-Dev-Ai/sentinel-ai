import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
NVIDIA_NIM_API_KEY = os.getenv("NVIDIA_NIM_API_KEY", "")
NVIDIA_NIM_BASE_URL = os.getenv("NVIDIA_NIM_BASE_URL", "https://integrate.api.nvidia.com/v1")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
SAMBANOVA_API_KEY = os.getenv("SAMBANOVA_API_KEY", "")
COHERE_API_KEY = os.getenv("COHERE_API_KEY", "")
CEREBRAS_API_KEY = os.getenv("CEREBRAS_API_KEY", "")
HEVA_E2E = os.getenv("HEVA_E2E", "0") == "1"

RECOVERY_BUDGET_PER_SUBTASK = int(os.getenv("RECOVERY_BUDGET_PER_SUBTASK", "3"))
MAX_AGENT_STEPS = int(os.getenv("MAX_AGENT_STEPS", "25"))
TOOL_TIMEOUT_SECONDS = int(os.getenv("TOOL_TIMEOUT_SECONDS", "30"))

PROVIDER_TIMEOUT_SECONDS = int(os.getenv("PROVIDER_TIMEOUT_SECONDS", "60"))

# Dynamic Model Tiers mapped to multiple providers for fallback
MODEL_TIERS = {
    "strategic": [
        {"provider": "openrouter", "model": "anthropic/claude-3.5-sonnet", "is_preferred": True, "is_free": False},
        {"provider": "cohere", "model": "command-r-plus-08-2024", "is_preferred": False, "is_free": True},
        {"provider": "openrouter", "model": "openai/gpt-4o", "is_preferred": True, "is_free": False},
    ],
    "coding": [
        {"provider": "sambanova", "model": "Meta-Llama-3.1-70B-Instruct", "is_preferred": False, "is_free": True},
        {"provider": "groq", "model": "llama-3.3-70b-versatile", "is_preferred": False, "is_free": True},
        {"provider": "openrouter", "model": "meta-llama/llama-3.3-70b-instruct", "is_preferred": True, "is_free": False},
    ],
    "fast_eval": [
        {"provider": "nvidia_nim", "model": "meta/llama-3.1-8b-instruct", "is_preferred": True, "is_free": False},
        {"provider": "cerebras", "model": "gemma-4-31b", "is_preferred": False, "is_free": True},
        {"provider": "groq", "model": "llama-3.1-8b-instant", "is_preferred": False, "is_free": True},
    ]
}

EVAL_REPORTS_DIR = WORKSPACE_ROOT / "eval" / "reports"

