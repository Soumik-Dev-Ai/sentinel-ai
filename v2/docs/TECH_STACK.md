# Sentinel AI 2.0 — Technology Stack & Infrastructure Specification

## 1. System Technology Matrix

```text
+---------------------------------------------------------------------------------------------------------+
|                                        SENTINEL AI 2.0 ARCHITECTURE                                     |
+---------------------------------------------------------------------------------------------------------+
|  Frontend Presentation Layer:                                                                           |
|  - Framework: React 18.2 (Concurrent Mode, Hooks, StrictMode)                                           |
|  - Build Tool: Vite 5.1 (ESBuild HMR, Rollup Production Bundler)                                        |
|  - Language: TypeScript 5.3 (Strict Type Checking)                                                      |
|  - Interactive Graph Canvas: ReactFlow 11.11 (Node-Edge DAG Visualization)                               |
|  - Animation: Framer Motion 11.0 (Spring Physics, State Transitions)                                     |
|  - Styling: Tailwind CSS 3.4 (JIT Compiler, Custom Developer Dark Theme)                                |
|  - Icons: Lucide React 0.359 (Tree-shakable SVG Icons)                                                  |
+---------------------------------------------------------------------------------------------------------+
|  Real-Time Transport Layer:                                                                             |
|  - Transport: Full-Duplex WebSockets (/ws) with JSON Event Streaming                                    |
|  - Sequence Ordering: Thread-safe EventBus with Monotonically Increasing Sequence IDs                    |
+---------------------------------------------------------------------------------------------------------+
|  Backend Orchestration Layer:                                                                           |
|  - Runtime: Python 3.11+ (Standard Library ast, subprocess, tempfile)                                   |
|  - Web Framework: FastAPI 0.110 (Asynchronous Route Handlers, Starlette WebSocket Core)                 |
|  - ASGI Server: Uvicorn 0.29 (UVLoop Event Loop Integration)                                           |
|  - Data Contracts: Pydantic v2.6 (Fast Rust-Backed Parsing and Schema Validation)                         |
|  - Local Database: SQLite3 (Structured Run History and Telemetry Storage)                              |
|  - Vector Memory: Custom NumPy-Based TF-IDF VectorStore (~/.sentinel_ai/memory)                         |
+---------------------------------------------------------------------------------------------------------+
|  Inference Routing Layer:                                                                               |
|  - Client SDK: OpenAI Python SDK 1.25+ (Universal /v1/chat/completions Interface)                       |
|  - Model Tiers: strategic, coding, fast_eval                                                            |
|  - Providers: Groq, NVIDIA NIM, OpenRouter, SambaNova, OpenCode, Cohere, Cerebras                       |
+---------------------------------------------------------------------------------------------------------+
```

---

## 2. Complete Repository File Structure

```text
Sentinel AI/
├── backend/
│   ├── db/
│   │   ├── __init__.py
│   │   └── store.py             # SQLite3 run history and telemetry persistence
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── contracts.py         # Provider and Reply base abstract interfaces
│   │   ├── router.py            # Multi-tier routing engine and dynamic failover
│   │   ├── openai_provider.py   # Base OpenAI client wrapper with TPD model rotation
│   │   ├── groq_provider.py     # Groq provider configuration
│   │   ├── nvidia_nim_provider.py # NVIDIA NIM provider configuration
│   │   ├── openrouter_provider.py # OpenRouter free-tier provider
│   │   ├── sambanova_provider.py  # SambaNova provider configuration
│   │   ├── opencode_provider.py   # OpenCode provider configuration
│   │   ├── cohere_provider.py     # Cohere provider with rate throttle
│   │   └── cerebras_provider.py   # Cerebras high-speed inference
│   ├── memory/
│   │   ├── __init__.py
│   │   └── vector_store.py      # TF-IDF local vector storage for RAG recall
│   ├── orchestrator/
│   │   ├── __init__.py
│   │   ├── base.py              # EventBus, Agent base class, AgentContext, AgentEvent
│   │   ├── orchestrator.py      # Tree-of-Thought strategic planning agent
│   │   ├── coder.py             # RAG-assisted code synthesis agent with AST sanitizer
│   │   ├── critic.py            # LLM-as-a-Judge review agent with rubric scoring
│   │   ├── executor.py          # Sandboxed subprocess runner and traceback parser
│   │   ├── retry.py             # Adaptive failure classification (syntax/logic/external)
│   │   ├── escalation.py        # Human-in-the-loop escalation manager
│   │   ├── cost.py              # Real-time token and USD budget telemetry tracker
│   │   └── pipeline.py          # Master MultiAgentPipeline execution coordinator
│   ├── safety/
│   │   ├── __init__.py
│   │   └── guardrails.py        # Pre-execution AST security scanner
│   ├── server/
│   │   ├── __init__.py
│   │   └── server.py            # FastAPI WebSocket server and HTTP endpoints
│   ├── telemetry/
│   │   ├── __init__.py
│   │   └── tracing.py           # Trace spans and execution attribute logger
│   ├── tests/
│   │   └── unit/                # 155 unit tests covering all components offline
│   ├── config.py                # Global settings, model tiers, and API keys
│   └── eval_suite.py            # Evaluation Lab A/B comparative benchmark engine
│
├── frontend/
│   ├── index.html
│   ├── package.json             # NPM dependencies
│   ├── vite.config.ts           # Vite build and proxy configuration
│   ├── tailwind.config.js       # Tailwind CSS theme extension
│   ├── tsconfig.json            # TypeScript strict compiler options
│   └── src/
│       ├── App.tsx              # Main application shell
│       ├── main.tsx             # React DOM entry point
│       ├── types.ts             # TypeScript event and telemetry schemas
│       └── components/
│           ├── AgentGraph.tsx   # ReactFlow live execution canvas
│           ├── Terminal.tsx     # Streaming logs and execution console
│           ├── Telemetry.tsx    # Real-time token and USD cost counters
│           ├── EscalationModal.tsx # Interactive human-in-the-loop dialog
│           └── EvaluationLab.tsx   # A/B benchmark evaluation dashboard
│
├── docs/                        # Complete project documentation
│   ├── ARCHITECTURE.md          # Multi-agent system architecture
│   ├── PRD.md                   # Product requirements document
│   ├── TECH_STACK.md            # Technology stack specification
│   ├── TESTING_PLAN.md          # Testing and verification plan
│   ├── IMPLEMENTATION_ORDER.md  # 5-phase execution milestones
│   ├── BENCHMARK_REPORT.md      # Evaluation Lab benchmark report
│   └── legacy_v1/               # Preserved v1.0 documentation archive
│
├── local_test_report/           # Evaluation Lab benchmark outputs (JSON traces)
├── run_custom_test.py           # Evaluation Lab benchmark entry script
├── requirements.txt             # Python runtime dependencies
└── README.md                    # Project quickstart and overview
```

---

## 3. Dependency Manifests & Rationale

### 3.1 Backend Dependencies (`Sentinel AI/requirements.txt`)
| Dependency | Version | Purpose & Rationale |
| :--- | :--- | :--- |
| `fastapi` | `0.110.0` | Asynchronous API and WebSocket framework. |
| `uvicorn[standard]` | `0.29.0` | Production ASGI web server with `uvloop` for low-latency concurrency. |
| `pydantic` | `2.6.4` | Rust-accelerated schema validation and serialization. |
| `pydantic-settings` | `2.2.1` | Environment variable parsing and `.env` file management. |
| `openai` | `1.25.0` | Universal client library for all OpenAI-compatible endpoints. |
| `numpy` | `1.26.4` | High-performance vector math for TF-IDF cosine similarity calculations. |
| `pytest` | `8.1.1` | Test runner for executing the 155-test unit suite. |
| `pytest-asyncio` | `0.23.6` | Async testing fixture support for WebSocket endpoints. |
| `pytest-timeout` | `2.3.1` | Prevents runaway subprocess executions during test runs. |
| `python-dotenv` | `1.0.1` | Automatic `.env` secret loading. |

### 3.2 Frontend Dependencies (`Sentinel AI/frontend/package.json`)
| Dependency | Version | Purpose & Rationale |
| :--- | :--- | :--- |
| `react` / `react-dom` | `^18.2.0` | Core reactive UI engine with concurrent rendering capabilities. |
| `reactflow` | `^11.11.0` | Node-edge DAG rendering for the live multi-agent execution canvas. |
| `framer-motion` | `^11.0.0` | Fluid animations for stage transitions and escalation dialogs. |
| `lucide-react` | `^0.359.0` | Lightweight SVG developer console icons. |
| `tailwindcss` | `^3.4.1` | Utility-first JIT styling with sub-20KB production bundle size. |
| `typescript` | `^5.3.3` | Type safety matching backend Pydantic schemas. |
| `vite` | `^5.1.0` | Sub-second Hot Module Replacement (HMR) and optimized build bundling. |

---

## 4. Multi-Tier Provider Routing & Configuration

Sentinel AI 2.0 configures 3 model tiers in [`backend/config.py`](file:///c:/Users/user/projects/self%20correcting%20multi%20agent/Sentinel%20AI/backend/config.py):

```python
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
```

### Provider Configuration Matrix:
| Provider | Environment Variable Key | Base URL | Model Indicators Used |
| :--- | :--- | :--- | :--- |
| **Groq** | `GROQ_API_KEY` | `https://api.groq.com/openai/v1` | `llama-3.3-70b-versatile`, `qwen3.8-27b`, `llama-3.1-8b-instant` |
| **NVIDIA NIM** | `NVIDIA_NIM_API_KEY` | `https://integrate.api.nvidia.com/v1` | `nemotron-3-super-120b`, `kimi` |
| **OpenRouter** | `OPENROUTER_API_KEY` | `https://openrouter.ai/api/v1` | Dynamic discovery prioritizing `:free` endpoints |
| **SambaNova** | `SAMBANOVA_API_KEY` | `https://api.sambanova.ai/v1` | `Meta-Llama-3.3-70B-Instruct`, `gemma-4-31B-it` |
| **OpenCode** | `OPEN_CODE_API_KEY` | `https://opencode.ai/inference/openai/v1` | Dynamic catalog models |
| **Cohere** | `COHERE_API_KEY` | `https://api.cohere.ai/v1` | `command-r-plus-08-2024` (Throttled with 6s rate limit) |
| **Cerebras** | `CEREBRAS_API_KEY` | `https://api.cerebras.ai/v1` | `llama3.1-8b`, `llama3.1-70b` |

---

## 5. Environment Variables Reference (`.env`)

```bash
# Server Configuration
PORT=8000
HOST=127.0.0.1
PROVIDER_TIMEOUT_SECONDS=90
PROVIDER_CALL_TIMEOUT_SECONDS=35
TOOL_TIMEOUT_SECONDS=30
RECOVERY_BUDGET_PER_SUBTASK=3
MAX_AGENT_STEPS=25

# Inference Provider API Keys (At least one required for live inference)
GROQ_API_KEY="gsk_..."
NVIDIA_NIM_API_KEY="nvapi-..."
OPENROUTER_API_KEY="sk-or-..."
SAMBANOVA_API_KEY="..."
OPEN_CODE_API_KEY="..."
COHERE_API_KEY="..."
CEREBRAS_API_KEY="..."
```
