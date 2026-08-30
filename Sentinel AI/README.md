# Sentinel AI • Self-Correcting Agent

Sentinel AI is a specialized, autonomous AI coding agent designed to write, test, and self-correct its own code in real-time. Built with a custom ReAct (Reasoning and Acting) framework, Sentinel doesn't just generate text—it actively interacts with a secure local workspace to compile code, catch terminal errors, and dynamically rewrite its logic until the code passes all constraints.

## ✨ Features

- **Autonomous Self-Correction:** When the agent encounters a runtime or syntax error, it parses the standard error (stderr) from the terminal and automatically regenerates the corrected code.
- **Real-Time WebSocket Streaming:** The AI's thoughts and terminal outputs are streamed character-by-character to the frontend for a live, transparent view of the agent's decision-making process.
- **Isolated Execution Workspace:** The agent operates inside a temporary, isolated sandbox where it can safely read, write, and execute Python scripts.
- **Dynamic UI/UX:** Built with Framer Motion, the interface smoothly transitions from a split-pane active execution view into a unified, beautifully rendered Markdown final report.

## 🛠️ Technology Stack

**Frontend:**
- React 18
- Vite
- Tailwind CSS
- Framer Motion (Animations)
- React-Markdown (Report Rendering)

**Backend:**
- Python 3.10+
- FastAPI (WebSocket & REST API)
- Uvicorn
- Custom ReAct Agent Framework
- LLM Integration via OpenRouter (Claude 3.5 Sonnet / GPT-4o)

## 🚀 Getting Started

### Prerequisites
- Node.js (v18+)
- Python (3.10+)
- An API Key from OpenRouter, Groq, or NVIDIA NIM.

### Backend Setup
1. Navigate to the root directory.
2. Create a virtual environment and install dependencies:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```
3. Create a `.env` file in the root directory and add your API keys:
   ```env
   OPENROUTER_API_KEY=your_api_key_here
   ```
4. Start the FastAPI server:
   ```bash
   python -m uvicorn backend.server.server:app --host 0.0.0.0 --port 9000
   ```

### Frontend Setup
1. Open a new terminal and navigate to the frontend directory:
   ```bash
   cd frontend
   ```
2. Install dependencies:
   ```bash
   npm install
   ```
3. Start the Vite development server:
   ```bash
   npm run dev
   ```
4. Open your browser to `http://localhost:5173`.

## 🧠 How It Works (The ReAct Loop)

1. **Trigger:** The user submits a goal via the React frontend over a WebSocket connection.
2. **Think:** The LLM evaluates the goal and streams its reasoning to the Live Terminal.
3. **Act:** The LLM invokes backend tools (e.g., `write_file`, `run_python`). 
4. **Observe:** The backend executes the code natively. If the script crashes, the backend catches the terminal traceback and feeds it directly back to the LLM.
5. **Correct:** The LLM recognizes the error, explicitly overwrites the buggy file with corrected logic, and pushes a UI update to instantly regenerate the code on the frontend.
