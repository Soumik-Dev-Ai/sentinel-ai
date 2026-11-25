# Tech Stack — Self-Correcting Multi-Step Agent

## 1. Runtime & Languages
- **Python 3.12** (3.11+ acceptable; uses `enum`, `dataclasses`, `typing` features).
- Type-strict: `mypy --strict` targeted; **pydantic v2** for all tool I/O schemas and `WorkingMemory`/`StepRecord`/`UnresolvableRecord` types.

## 2. Agent & Tools
| Concern | Choice | Rationale |
|---------|--------|-----------|
| LLM SDKs | `anthropic`, `openai`, `httpx` (for Ollama) | Permitted by assignment; multi-provider fallback. |
| Tool libs | `subprocess`, `pathlib`, `shutil`, `pydantic` | All explicitly permitted standard libs. |
| Schema validation | `pydantic v2` (runtime) | Tool args + returns validated; violations become `ToolFailure(shape_violation)`. |
| Sandbox | `subprocess.run(timeout, cwd=tempdir, env=blocked_net)` | Process isolation without containers. |
| POSIX hardening | `resource.setrlimit` (optional) | CPU/filesize caps. Windows: timeout+cwd+env only (documented). |

## 3. Observability & Viewer
| Concern | Choice |
|---------|--------|
| Logger | custom JSON writer; one JSON run file in `eval/reports/<run_id>.json` |
| CLI viewer | `rich` (tables, tracebacks, syntax-highlighted reasoning) |
| HTML viewer | `jinja2` template -> single self-contained `.html` per run |

## 4. Testing
| Concern | Choice |
|---------|--------|
| Framework | `pytest`, `pytest-cov`, `pytest-timeout` |
| HTTP mocking | Scripted providers in tests (no network in unit/integration) |
| Time mocking | Real `datetime.now(UTC)`; deterministic via `MockProvider` canned Replies |
| Fixtures | `MockProvider` returning canned `Reply` objects -> all unit/integration tests offline + deterministic |

## 5. Eval & Metrics
| Concern | Choice |
|---------|--------|
| Goal definitions | `PyYAML` (`eval/goals.yaml`) |
| Metrics | computed in `eval/metrics.py`; persisted as `metrics.csv` + `metrics.md` |
| Comparison | `eval/comparison.md` (self-correcting vs baseline side-by-side via `rich`-rendered markdown) |

## 6. Code Quality & Workflow
| Concern | Choice |
|---------|--------|
| Lint/format | `ruff` (lint + format) |
| Types | `mypy --strict src` |
| Hooks | `pre-commit` (ruff + mypy + pytest-gate) |
| Secrets | `python-dotenv` for `.env`; `.gitignore` covers `.env`, `eval/reports/`, `__pycache__/`, `.mypy_cache/`, `.ruff_cache/` |
| Commit plan | small, descriptive commits per module (see `IMPLEMENTATION_ORDER.md` section 5) |

## 7. Demo Capture
- `demos/demo_script.md` storyboard ensures GIF captures >=1 visible self-correction.
- Capture via `asciinema rec` -> export to GIF, or `rich` Live recording -> GIF.

## 8. Dependency Inventory (`pyproject.toml`)

### Runtime
```
anthropic>=0.40
openai>=1.50
httpx>=0.27
pydantic>=2.7
rich>=13.7
jinja2>=3.1
pyyaml>=6.0
python-dotenv>=1.0
```

### Dev / Test
```
pytest>=8.2
pytest-cov>=5.0
pytest-timeout>=2.3
ruff>=0.5
mypy>=1.10
pre-commit>=3.7
```

### Install command
```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -e ".[dev]"         # if pyproject extras defined, else:
pip install -r requirements.txt
```

## 9. Constraint Compliance Check
| Assignment rule | Our compliance |
|-----------------|----------------|
| No LangChain / LlamaIndex / AutoGen / CrewAI / agent frameworks | YES — we build the loop ourselves in `src/agent/runner.py`. |
| No pre-built agent scaffolding | YES — only `anthropic` / `openai` SDKs (chat APIs); we wrap them in our own `Reply` contract. |
| LLM APIs allowed (OpenAI, Anthropic, open models) | YES — multi-LLM fallback chain. |
| Standard tool libs allowed (`requests`, `bs4`, `pandas`) | YES — we use `subprocess`, `pathlib`, `pydantic`, `pyyaml` (subset appropriate to the code domain). |

## 10. Version Pinning Policy
- Lower-bound pins (e.g. `pydantic>=2.7`) for flexibility; `uv.lock`/`requirements.lock` generated for reproducible eval runs.
- Python: pinned to `3.12` in `pyproject.toml` `requires-python = ">=3.12"`.
