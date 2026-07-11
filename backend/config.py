import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
NVIDIA_NIM_API_KEY = os.getenv("NVIDIA_NIM_API_KEY", "")
NVIDIA_NIM_BASE_URL = os.getenv("NVIDIA_NIM_BASE_URL", "https://integrate.api.nvidia.com/v1")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
HEVA_E2E = os.getenv("HEVA_E2E", "0") == "1"

RECOVERY_BUDGET_PER_SUBTASK = int(os.getenv("RECOVERY_BUDGET_PER_SUBTASK", "3"))
MAX_AGENT_STEPS = int(os.getenv("MAX_AGENT_STEPS", "25"))
TOOL_TIMEOUT_SECONDS = int(os.getenv("TOOL_TIMEOUT_SECONDS", "30"))

PROVIDER_TIMEOUT_SECONDS = int(os.getenv("PROVIDER_TIMEOUT_SECONDS", "60"))


def _available_providers() -> list[str]:
    chain: list[str] = []
    # Always prioritize OpenRouter (GPT-4o / Claude) for perfect Tool Calling!
    if OPENROUTER_API_KEY:
        chain.append("openrouter")
    if GROQ_API_KEY:
        chain.append("groq")
    if NVIDIA_NIM_API_KEY:
        chain.append("nvidia_nim")
    chain.append("local")
    return chain


LLM_CHAIN: list[str] = _available_providers()

EVAL_REPORTS_DIR = WORKSPACE_ROOT / "eval" / "reports"

