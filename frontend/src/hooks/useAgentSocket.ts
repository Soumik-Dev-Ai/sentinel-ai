import { useCallback, useEffect, useRef, useState } from "react";
import type { TerminalLine, CodeLine } from "../services/agentBridge";
import {
  getSimulatedResult,
  agentResultToDisplay,
} from "../services/agentBridge";

const WS_URL = import.meta.env.VITE_WS_URL || "ws://localhost:5173/ws/run";

export type AgentPhase = "idle" | "running" | "done" | "error";

interface AgentState {
  terminalLines: TerminalLine[];
  codeLines: CodeLine[];
  phase: AgentPhase;
  finalReport: string;
  error: string | null;
  metrics: Record<string, number>;
  triggerRun: () => void;
}

export function useAgentSocket(goal: string, inputText = ""): AgentState {
  const [runId, setRunId] = useState(0);
  const [terminalLines, setTerminalLines] = useState<TerminalLine[]>([]);
  const [codeLines, setCodeLines] = useState<CodeLine[]>([]);
  const [phase, setPhase] = useState<AgentPhase>("idle");
  const [finalReport, setFinalReport] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [metrics, setMetrics] = useState<Record<string, number>>({});
  const thoughtBuffer = useRef("");
  const actionBuffer = useRef("");
  const simTimers = useRef<ReturnType<typeof setTimeout>[]>([]);

  useEffect(() => {
    if (!goal) return;

    setTerminalLines([]);
    setCodeLines([]);
    setPhase("running");
    setFinalReport("");
    setError(null);
    setMetrics({});
    thoughtBuffer.current = "";
    actionBuffer.current = "";

    let cancelled = false;
    let ws: WebSocket | null = null;

    const startSim = () => {
      const result = getSimulatedResult(goal);
      const { terminalLines: t, codeLines: c, finalOutput } =
        agentResultToDisplay(result);

      const timers: ReturnType<typeof setTimeout>[] = [];
      t.forEach((line) => {
        const t2 = setTimeout(() => {
          if (!cancelled) setTerminalLines((p) => [...p, line]);
        }, line.delay);
        timers.push(t2);
      });
      c.forEach((line) => {
        const t2 = setTimeout(() => {
          if (!cancelled) setCodeLines((p) => [...p, line]);
        }, line.delay);
        timers.push(t2);
      });
      const lastDelay = Math.max(0, ...t.map((l) => l.delay), ...c.map((l) => l.delay));
      timers.push(
        setTimeout(() => {
          if (!cancelled) {
            setPhase("done");
            setFinalReport(finalOutput);
            setMetrics({
              steps: result.steps_taken,
              selfCorrections: result.self_corrections,
              providerSwitches: result.metrics.provider_switches,
            });
          }
        }, lastDelay + 1500)
      );
      simTimers.current = timers;
    };

    try {
      ws = new WebSocket(WS_URL);
      ws.onopen = () => {
        if (cancelled) { ws?.close(); return; }
        ws?.send(JSON.stringify({ goal, input: inputText }));
      };
      ws.onmessage = (event) => {
        if (cancelled) return;
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === "terminal_line") {
            setTerminalLines((prev) => [
              ...prev,
              { text: msg.text, type: (msg.line_type as TerminalLine["type"]) || "info", delay: 0 },
            ]);
          } else if (msg.type === "stream_thought") {
            const token = msg.token || "";
            setTerminalLines((prev) => {
              if (prev.length === 0) return prev;
              const newLines = [...prev];
              const last = newLines[newLines.length - 1];
              if (last.type === "info" && last.text.includes("Initializing AI reasoning step")) {
                last.text += "\n" + token;
                last.type = "step";
              } else if (last.type === "step") {
                last.text += token;
              } else {
                newLines.push({ text: "Thinking: " + token, type: "step", delay: 0 });
              }
              return newLines;
            });
          } else if (msg.type === "stream_action") {
            const token = msg.token || "";
            actionBuffer.current += token;
            const match = actionBuffer.current.match(/"content"\s*:\s*"(.*)/s);
            if (match) {
              let rawContent = match[1];
              rawContent = rawContent.replace(/\\n/g, "\n").replace(/\\"/g, "\"").replace(/\\\\/g, "\\");
              const lines = rawContent.split("\n").map(line => ({
                text: line,
                type: (line.trim().startsWith("#") ? "comment" : "code") as CodeLine["type"],
                delay: 0
              }));
              setCodeLines([
                { text: `# generating code...`, type: "comment", delay: 0 },
                ...lines
              ]);
            }
          } else if (msg.type === "code_update") {
            actionBuffer.current = "";
            thoughtBuffer.current = "";
            const path = msg.path || "unknown";
            const content: string = msg.content || "";
            
            setCodeLines([
              { text: `# ${path}`, type: "comment", delay: 0 },
              ...content.split("\n").map((line: string) => ({
                text: line,
                type: (line.trim().startsWith("#") ? "comment" : "code") as CodeLine["type"],
                delay: 0,
              })),
              { text: "", type: "blank" as const, delay: 0 },
            ]);
          } else if (msg.type === "completed") {
            const r = msg.result;
            setMetrics({
              steps: r.steps_taken,
              selfCorrections: r.self_corrections,
              providerSwitches: r.metrics?.provider_switches ?? 0,
            });
            let finalOut = r.final_output || "No output";
            if (r.generated_code && Object.keys(r.generated_code).length > 0) {
              finalOut += "\n\n### Generated Code:\n";
              for (const [filename, content] of Object.entries(r.generated_code)) {
                finalOut += `\n#### ${filename}\n\`\`\`python\n${content}\n\`\`\`\n`;
              }
            }
            setFinalReport(finalOut);
            setPhase("done");
          } else if (msg.type === "error") {
            setError(msg.message || "Unknown error");
            setPhase("error");
          }
        } catch {
          // ignore malformed messages
        }
      };
      ws.onerror = () => {
        if (cancelled) return;
        ws?.close();
        startSim();
      };
      ws.onclose = () => {
        if (!cancelled && phase === "running" && terminalLines.length === 0) {
          startSim();
        }
      };
    } catch {
      if (!cancelled) startSim();
    }

    return () => {
      cancelled = true;
      simTimers.current.forEach(clearTimeout);
      simTimers.current = [];
      ws?.close();
    };
  }, [goal, inputText, runId]);

  const triggerRun = useCallback(() => setRunId((n) => n + 1), []);

  return {
    terminalLines, codeLines, phase, finalReport, error, metrics,
    triggerRun,
  };
}
