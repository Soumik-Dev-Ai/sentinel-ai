# Sentinel AI — Self-Correcting Multi-Agent System

> A multi-agent AI system that writes, critiques, executes, and self-corrects code autonomously.

![Architecture](./architecture.html) <!-- or embed a screenshot -->

## How It Works

1. **Orchestrator** plans via Tree-of-Thought (3 candidate paths → best one)
2. **Coder** writes Python code for each subtask
3. **Critic** (LLM-as-a-Judge) scores code 0-100; rejects if < 80
4. **Executor** runs the code in a sandboxed subprocess
5. **RetryRouter** classifies failures (syntax → line_patch, logic → rewrite, external → backoff)
6. **EscalationManager** triggers human-in-the-loop if confidence < 0.50 after 2 retries
7. **VectorStore** persists solved/error patterns for RAG retrieval across runs

## Key Features

- **6-Provider LLM Routing**: Groq → SambaNova → Cohere → Cerebras → OpenRouter → NVIDIA NIM (backup)
- **Cost-Aware Routing**: Prioritizes free-tier providers; tracks token usage + USD cost in real-time
- **Live Execution Graph**: ReactFlow visualization of the agent pipeline
- **Evaluation Lab**: A/B comparison of self-correction ON vs OFF with downloadable reports
- **Human-in-the-Loop**: Confidence-based escalation modal with 5-minute timeout

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11+, FastAPI, WebSocket |
| Frontend | React 18, TypeScript, Vite, Framer Motion, ReactFlow |
| LLM Providers | Groq, SambaNova, Cohere, Cerebras, OpenRouter, NVIDIA NIM |
| Memory | NumPy-based VectorStore with local embeddings |
| Deployment | Render (backend), Vercel (frontend) |

## Benchmark Results

| Metric | Baseline (SC OFF) | Self-Correction ON |
|---|---|---|
| Completion Rate | 60% | 100% |
| Avg Steps | 3.3 | 2.0 |
| Avg Time | 139.7s | 32.6s |

## Getting Started

```bash
# Backend
cd "Sentinel AI"
pip install -r requirements.txt
cp .env.example .env  # Add your API keys
uvicorn backend.server.server:app --reload

# Frontend
cd frontend
npm install
npm run dev
```
