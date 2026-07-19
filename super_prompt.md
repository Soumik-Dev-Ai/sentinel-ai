# Sentinel AI 2.0: Enterprise Upgrade Prompt

**Role & Context:**
You are an elite Principal AI Engineer and System Architect. I have an existing project called "Sentinel AI," an autonomous, self-correcting coding agent. The current architecture consists of a React/Vite/Tailwind frontend and a Python/FastAPI backend connected via WebSockets. The backend currently uses a standard ReAct (Reasoning and Acting) loop where a single agent reads a goal, generates Python code, runs it in a local temporary directory, catches `stderr` on failure, and autonomously rewrites the code to fix bugs.

**The Objective:**
I need to upgrade this codebase into a state-of-the-art, enterprise-grade multi-agent system. I want a complete, polished, production-ready system. You must implement the following advanced architectural upgrades, ensuring seamless integration between the frontend and backend. 

*Note: Do NOT implement Docker sandboxing; we will continue using local temporary directories for execution.*

### Core Architectural Upgrades:

**1. Multi-Agent Orchestration (The Engine)**
Refactor the single ReAct loop into a coordinated Team of Specialists:
- **Orchestrator Agent:** Decomposes the user's goal into subtasks and routes them.
- **Coder Agent:** Specialized exclusively in writing optimal, clean code.
- **Critic Agent (LLM-as-a-Judge):** Reviews the Coder's output *before* execution, scoring it (0-10) on correctness and edge-cases. If the score is <8, it rejects the code and forces a rewrite.
- **Executor Agent:** Runs the code, parses tracebacks, and reports back to the Orchestrator.

**2. Tree-of-Thought Planning**
Instead of linear ReAct, the Orchestrator must use Tree-of-Thought. Before acting, it must generate 3 distinct approach paths, evaluate the confidence of each, and select the highest-scoring path to execute.

**3. Persistent Memory (RAG / Vector DB)**
Integrate a lightweight vector database (e.g., ChromaDB or local FAISS). The system must store summaries of solved goals, encountered errors, and successful correction strategies. Before the Coder acts, it must query the Vector DB to retrieve past learnings (e.g., "Last time I saw this AssertionError, I solved it by doing X").

**4. Adaptive Retry Strategies**
Replace the static retry loop. Implement a strategy router that categorizes failures:
- *Syntax Error* -> Trigger targeted line-level patch.
- *Logic Error / Wrong Output* -> Trigger full algorithm rewrite.
- *Network/External Error* -> Trigger exponential backoff.

**5. Confidence-Based Escalation (Human-in-the-Loop)**
If the system attempts 2 self-corrections on the same subtask and its internal confidence score drops below 50%, the agent must **escalate**. It should pause execution, send a `NEEDS_HUMAN_REVIEW` event over the WebSocket, and ask the user a clarifying question before continuing.

### Frontend UI / UX Upgrades:

**6. Real-Time Execution Graph Visualization**
Update the React frontend to parse the new Multi-Agent flow. Render a live, dynamic flowchart (using React Flow or Framer Motion). Each node represents an agent's action (e.g., "Orchestrator Planning", "Coder Writing", "Critic Judging"). Nodes should glow green on success and red on failure, drawing arrows to show the correction loop.

**7. Cost & Token Budget Tracking**
The FastAPI backend must track input/output tokens for every LLM call across all agents. Stream this data to the frontend via WebSockets. The React UI must display a live telemetry dashboard showing:
- Real-time token consumption.
- Estimated cost in USD (based on Claude 3.5 Sonnet / DeepSeek pricing).
- Budget remaining for the current task.

### Implementation Constraints & Output Requirements:
1. **Modularity:** Do not dump everything into one file. Create a clean modular structure (e.g., `agents/coder.py`, `memory/vector_store.py`, `ui/components/ExecutionGraph.tsx`).
2. **Robustness:** Ensure WebSocket disconnections and API rate limits are handled gracefully.
3. **Completeness:** Provide the complete, exact code for both the Python backend and React frontend. Do not use placeholders like `// ... rest of code`. 
4. **Step-by-Step Execution:** Start by providing the updated `requirements.txt` and `package.json`, then give me the core backend orchestrator, followed by the specific agents, the WebSocket server updates, and finally the React components.

Take a deep breath and think step-by-step. Deliver a masterpiece.
