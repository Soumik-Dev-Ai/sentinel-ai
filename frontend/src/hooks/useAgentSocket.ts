import { useCallback, useEffect, useRef, useState } from "react";
import type { TerminalLine, CodeLine } from "../services/agentBridge";
import {
  getSimulatedResult,
  agentResultToDisplay,
} from "../services/agentBridge";
import type {
  GraphNode,
  GraphEdgeFE,
  TelemetryUpdate,
  NeedsHumanReview,
  CriticVerdict,
  RetryStrategyEvent,
  MemoryActivity,
} from "../types/multiagent";

const WS_URL = import.meta.env.VITE_WS_URL || "ws://localhost:8000/ws/run";

export type AgentPhase = "idle" | "running" | "done" | "error";

export type RunMode = "multi" | "react";

interface MultiAgentMetrics {
  steps: number;
  selfCorrections: number;
  providerSwitches: number;
  tokensTotal: number;
  costTotalUsd: number;
  calls: number;
  budgetRemainingUsd: number | null;
  subtasksResolved: number;
  subtasksTotal: number;
  elapsedSeconds: number;
  memoryEntries: number;
}

interface AgentState {
  // legacy visual state
  terminalLines: TerminalLine[];
  codeLines: CodeLine[];
  phase: AgentPhase;
  finalReport: string;
  error: string | null;
  metrics: MultiAgentMetrics;

  // new multi-agent state
  graphNodes: GraphNode[];
  graphEdges: GraphEdgeFE[];
  telemetry: TelemetryUpdate | null;
  criticVerdicts: CriticVerdict[];
  retryStrategies: RetryStrategyEvent[];
  memoryActivity: MemoryActivity[];
  pendingReview: NeedsHumanReview | null;

  // live code stream
  liveCodeStream: string;

  // control
  triggerRun: () => void;
  sendEscalationAnswer: (escalation_id: string, answer: string) => void;
  dismissReview: () => void;
  wsRef: React.MutableRefObject<WebSocket | null>;
  startedAt: number | null;
}

const EMPTY_METRICS: MultiAgentMetrics = {
  steps: 0,
  selfCorrections: 0,
  providerSwitches: 0,
  tokensTotal: 0,
  costTotalUsd: 0,
  calls: 0,
  budgetRemainingUsd: null,
  subtasksResolved: 0,
  subtasksTotal: 0,
  elapsedSeconds: 0,
  memoryEntries: 0,
};

export function useAgentSocket(
  goal: string,
  inputText = "",
  mode: RunMode = "multi"
): AgentState {
  const [runId, setRunId] = useState(0);
  const [terminalLines, setTerminalLines] = useState<TerminalLine[]>([]);
  const [codeLines, setCodeLines] = useState<CodeLine[]>([]);
  const [phase, setPhase] = useState<AgentPhase>("idle");
  const [finalReport, setFinalReport] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [metrics, setMetrics] = useState<MultiAgentMetrics>(EMPTY_METRICS);

  // multi-agent state
  const [graphNodes, setGraphNodes] = useState<GraphNode[]>([]);
  const [graphEdges, setGraphEdges] = useState<GraphEdgeFE[]>([]);
  const [telemetry, setTelemetry] = useState<TelemetryUpdate | null>(null);
  const [criticVerdicts, setCriticVerdicts] = useState<CriticVerdict[]>([]);
  const [retryStrategies, setRetryStrategies] = useState<RetryStrategyEvent[]>([]);
  const [memoryActivity, setMemoryActivity] = useState<MemoryActivity[]>([]);
  const [pendingReview, setPendingReview] = useState<NeedsHumanReview | null>(null);
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [liveCodeStream, setLiveCodeStream] = useState<string>("");

  const thoughtBuffer = useRef("");
  const actionBuffer = useRef("");
  const streamCodeBuffer = useRef("");
  const simTimers = useRef<ReturnType<typeof setTimeout>[]>([]);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!goal) return;

    setTerminalLines([]);
    setCodeLines([]);
    setPhase("running");
    setFinalReport("");
    setError(null);
    setMetrics(EMPTY_METRICS);
    setGraphNodes([]);
    setGraphEdges([]);
    setTelemetry(null);
    setCriticVerdicts([]);
    setRetryStrategies([]);
    setMemoryActivity([]);
    setPendingReview(null);
    setStartedAt(Date.now());
    setLiveCodeStream("");
    thoughtBuffer.current = "";
    actionBuffer.current = "";
    streamCodeBuffer.current = "";

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
      const lastDelay = Math.max(
        0,
        ...t.map((l) => l.delay),
        ...c.map((l) => l.delay)
      );
      timers.push(
        setTimeout(() => {
          if (!cancelled) {
            setPhase("done");
            setFinalReport(finalOutput);
            setMetrics((m) => ({
              ...m,
              steps: result.steps_taken,
              selfCorrections: result.self_corrections,
              providerSwitches: result.metrics.provider_switches,
            }));
          }
        }, lastDelay + 1500)
      );
      simTimers.current = timers;
    };

    try {
      ws = new WebSocket(WS_URL);
      wsRef.current = ws;

      ws.onopen = () => {
        if (cancelled) {
          ws?.close();
          return;
        }
        // Use the structured "start" message so the backend selects multi mode.
        ws?.send(
          JSON.stringify({
            type: "start",
            goal,
            input: inputText,
            mode,
          })
        );
      };

      ws.onmessage = (event) => {
        if (cancelled) return;
        try {
          const msg = JSON.parse(event.data);
          handleMessage(msg);
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [goal, inputText, runId, mode]);

  /* ----------------------------------------------------------------------------
     Message handler — supports all legacy & new event types.
     ---------------------------------------------------------------------------- */

  const handleMessage = useCallback((msg: any) => {
    const type = msg.type as string;

    switch (type) {
      /* --- legacy terminal / streaming --- */
      case "terminal_line": {
        setTerminalLines((prev) => [
          ...prev,
          {
            text: msg.text ?? "",
            type: (msg.line_type as TerminalLine["type"]) || "info",
            delay: 0,
          },
        ]);
        break;
      }
      case "stream_thought": {
        const token = msg.token || "";
        setTerminalLines((prev) => {
          if (prev.length === 0) return prev;
          const newLines = [...prev];
          const last = newLines[newLines.length - 1];
          if (
            last.type === "info" &&
            last.text.includes("Initializing AI reasoning step")
          ) {
            last.text += "\n" + token;
            last.type = "step";
          } else if (last.type === "step") {
            last.text += token;
          } else {
            newLines.push({ text: "Thinking: " + token, type: "step", delay: 0 });
          }
          return newLines;
        });
        break;
      }
      case "stream_action": {
        const token = msg.token || "";
        actionBuffer.current += token;
        const match = actionBuffer.current.match(/"content"\s*:\s*"(.*)/s);
        if (match) {
          let rawContent = match[1];
          rawContent = rawContent
            .replace(/\\n/g, "\n")
            .replace(/\\"/g, '"')
            .replace(/\\\\/g, "\\");
          const lines = rawContent.split("\n").map((line) => ({
            text: line,
            type: (line.trim().startsWith("#")
              ? "comment"
              : "code") as CodeLine["type"],
            delay: 0,
          }));
          setCodeLines([
            { text: `# generating code...`, type: "comment", delay: 0 },
            ...lines,
          ]);
        }
        break;
      }
      case "code_update": {
        actionBuffer.current = "";
        thoughtBuffer.current = "";
        streamCodeBuffer.current = "";
        const path = msg.path || "unknown";
        const content: string = msg.content || "";
        setCodeLines([
          { text: `# ${path}`, type: "comment", delay: 0 },
          ...content.split("\n").map((line: string) => ({
            text: line,
            type: (line.trim().startsWith("#")
              ? "comment"
              : "code") as CodeLine["type"],
            delay: 0,
          })),
          { text: "", type: "blank" as const, delay: 0 },
        ]);
        setLiveCodeStream("");
        break;
      }

      /* --- new multi-agent events --- */
      case "agent_started": {
        setTerminalLines((prev) => [
          ...prev,
          {
            text: `▶ ${msg.agent || "agent"}: ${msg.label || ""}`,
            type: "step",
            delay: 0,
          },
        ]);
        break;
      }
      case "agent_finished": {
        setTerminalLines((prev) => [
          ...prev,
          {
            text: `✓ ${msg.agent || "agent"}: ${msg.status || "ok"}`,
            type: msg.status === "ok" || msg.status === "success" ? "success" : "error",
            delay: 0,
          },
        ]);
        break;
      }
      case "agent_stream": {
        // grouped multi-agent stream token (kind: thought or action)
        const token = msg.token || "";
        const kind = msg.kind || "thought";
        setTerminalLines((prev) => {
          if (prev.length === 0) {
            return [
              {
                text: `${msg.agent || "agent"} (${kind}): ` + token,
                type: kind === "action" ? "action" : "step",
                delay: 0,
              },
            ];
          }
          const newLines = [...prev];
          const last = newLines[newLines.length - 1];
          const tag = `[${msg.agent || "agent"}]`;
          if (
            (last.type === "step" || last.type === "action") &&
            last.text.startsWith(tag)
          ) {
            last.text += token;
          } else {
            newLines.push({
              text: `${tag} (${kind}) ${token}`,
              type: kind === "action" ? "action" : "step",
              delay: 0,
            });
          }
          return newLines;
        });
        // live code feed: accumulate action tokens, extract python code blocks
        if (kind === "action") {
          streamCodeBuffer.current += token;
          const codeMatch = streamCodeBuffer.current.match(/```python\n([\s\S]*?)```/);
          if (codeMatch) {
            setLiveCodeStream(codeMatch[1]);
          }
        }
        break;
      }

      case "graph_node": {
        const node = (msg as any) as GraphNode & { id: string };
        setGraphNodes((prev) => {
          const idx = prev.findIndex((n) => n.id === node.id);
          if (idx === -1) {
            const next: GraphNode = {
              id: node.id,
              label: node.label ?? node.id,
              agent: node.agent ?? "agent",
              status: (node.status as GraphNode["status"]) ?? "active",
              parent: node.parent,
              meta: node.meta,
              ts: msg.ts,
            };
            return [...prev, next];
          }
          const updated = [...prev];
          const cur = updated[idx];
          updated[idx] = {
            ...cur,
            ...{
              ...node,
              label: node.label ?? cur.label,
              agent: node.agent ?? cur.agent,
              status: (node.status as GraphNode["status"]) ?? cur.status,
              meta: node.meta ?? cur.meta,
            },
          };
          return updated;
        });
        // Auto-create edge if a parent is specified.
        if (msg.parent) {
          const edgeId = `${msg.parent}->${msg.id}`;
          setGraphEdges((prev) => {
            if (prev.some((e) => e.id === edgeId)) return prev;
            return [
              ...prev,
              {
                id: edgeId,
                source: msg.parent,
                target: msg.id,
                animated: msg.status === "active",
              },
            ];
          });
        }
        break;
      }

      case "graph_edge": {
        const edge = (msg as any) as GraphEdgeFE & { id: string };
        setGraphEdges((prev) => {
          if (prev.some((e) => e.id === edge.id)) return prev;
          return [
            ...prev,
            {
              id: edge.id,
              source: edge.source,
              target: edge.target,
              animated: edge.animated,
            },
          ];
        });
        break;
      }

      case "critic_verdict": {
        const v: CriticVerdict = {
          filename: msg.filename,
          passes: msg.passes,
          verdict: msg.verdict,
          scores: msg.scores,
          issues: msg.issues || [],
          fix_suggestions: msg.fix_suggestions || [],
        };
        setCriticVerdicts((prev) => [...prev, v]);
        setTerminalLines((prev) => [
          ...prev,
          {
            text: `[CRITIC] ${v.verdict} — score: ${v.scores.total}/100`,
            type: v.passes ? "success" : "error",
            delay: 0,
          },
        ]);
        break;
      }

      case "code_written": {
        const path = msg.path || "unknown";
        const content: string = msg.content || "";
        setCodeLines([
          { text: `# ${path}`, type: "comment", delay: 0 },
          ...content.split("\n").map((line: string) => ({
            text: line,
            type: (line.trim().startsWith("#")
              ? "comment"
              : "code") as CodeLine["type"],
            delay: 0,
          })),
          { text: "", type: "blank" as const, delay: 0 },
        ]);
        setLiveCodeStream("");
        streamCodeBuffer.current = "";
        break;
      }

      case "code_executed": {
        if (msg.ok) {
          setTerminalLines((prev) => [
            ...prev,
            {
              text: `[EXEC ✓] ${msg.filename} exit=${msg.exit_code}`,
              type: "success",
              delay: 0,
            },
          ]);
        } else {
          setTerminalLines((prev) => [
            ...prev,
            {
              text: `[EXEC ✗] ${msg.filename}: ${
                msg.error_type || "failure"
              }\n${(msg.details || JSON.stringify(msg.parsed_traceback || {})).slice(0, 400)}`,
              type: "error",
              delay: 0,
            },
          ]);
        }
        if (msg.stdout) {
          setTerminalLines((prev) => [
            ...prev,
            {
              text: `[stdout]\n${String(msg.stdout).slice(0, 600)}`,
              type: "success",
              delay: 0,
            },
          ]);
        }
        if (msg.stderr) {
          setTerminalLines((prev) => [
            ...prev,
            {
              text: `[stderr]\n${String(msg.stderr).slice(0, 600)}`,
              type: "error",
              delay: 0,
            },
          ]);
        }
        break;
      }

      case "retry_strategy": {
        const r: RetryStrategyEvent = {
          subtask_id: msg.subtask_id,
          category: msg.category,
          exception: msg.exception,
          strategy: msg.strategy,
          attempt: msg.attempt,
          wait_seconds: msg.wait_seconds,
          guidance: msg.guidance,
        };
        setRetryStrategies((prev) => [...prev, r]);
        setTerminalLines((prev) => [
          ...prev,
          {
            text: `[RETRY] ${r.subtask_id} — ${r.strategy} (attempt ${r.attempt}, ${r.category})"
                   \nguidance: ${r.guidance.slice(0, 240)}`,
            type: "recovery",
            delay: 0,
          },
        ]);
        break;
      }

      case "memory_recall": {
        setMemoryActivity((prev) => [
          ...prev,
          { kind: "solved", query: msg.query, n: msg.n },
        ]);
        setTerminalLines((prev) => [
          ...prev,
          {
            text: `[MEMORY] RAG recall (${msg.n} entries): ${
              (msg.query || "").slice(0, 80)
            }`,
            type: "success",
            delay: 0,
          },
        ]);
        break;
      }

      case "memory_stored": {
        setMemoryActivity((prev) => [
          ...prev,
          { kind: msg.kind, subtask_id: msg.subtask_id, filename: msg.filename },
        ]);
        break;
      }

      case "needs_human_review": {
        setPendingReview({
          escalation_id: msg.escalation_id,
          subtask_id: msg.subtask_id,
          question: msg.question,
          confidence: msg.confidence,
          context_summary: msg.context_summary || {},
          timeout_seconds: msg.timeout_seconds,
        });
        break;
      }

      case "resume_from_human": {
        setPendingReview(null);
        setTerminalLines((prev) => [
          ...prev,
          {
            text: `[HUMAN ✉] ${msg.subtask_id}: ${msg.answer}`,
            type: "success",
            delay: 0,
          },
        ]);
        break;
      }

      case "telemetry_update": {
        const tt: TelemetryUpdate = {
          total_input_tokens: msg.total_input_tokens || 0,
          total_output_tokens: msg.total_output_tokens || 0,
          total_tokens: msg.total_tokens || 0,
          total_cost_usd: msg.total_cost_usd || 0,
          per_agent: msg.per_agent || {},
          budget_remaining_tokens: msg.budget_remaining_tokens ?? null,
          budget_remaining_usd: msg.budget_remaining_usd ?? null,
          budget_exhausted: !!msg.budget_exhausted,
          budget_reason: msg.budget_reason || "",
          calls: msg.calls || 0,
        };
        setTelemetry(tt);
        setMetrics((m) => ({
          ...m,
          tokensTotal: tt.total_tokens,
          costTotalUsd: tt.total_cost_usd,
          calls: tt.calls,
          budgetRemainingUsd: tt.budget_remaining_usd,
        }));
        break;
      }

      case "step_recorded":
      case "correction_applied": {
        // legacy compat: emit a generic terminal line summary
        setTerminalLines((prev) => [
          ...prev,
          {
            text: `[${type}] step recorded`,
            type: "recovery",
            delay: 0,
          },
        ]);
        break;
      }

      case "completed": {
        const r = msg.result || {};
        setMetrics((m) => ({
          ...m,
          steps: r.steps_taken ?? m.steps,
          selfCorrections: r.self_corrections ?? m.selfCorrections,
          providerSwitches: r.metrics?.provider_switches ?? m.providerSwitches,
          subtasksResolved:
            (r.subtasks || []).filter((s: any) => s.resolved).length ?? 0,
          subtasksTotal: (r.subtasks || []).length ?? 0,
          elapsedSeconds: r.metrics?.elapsed_seconds ?? 0,
          memoryEntries: r.metrics?.memory_entries ?? 0,
          tokensTotal: r.metrics?.tokens_total ?? m.tokensTotal,
          costTotalUsd: r.metrics?.cost_total_usd ?? m.costTotalUsd,
          calls: r.metrics?.calls ?? m.calls,
          budgetRemainingUsd:
            r.metrics?.budget_remaining_usd ?? m.budgetRemainingUsd,
        }));
        let finalOut: string =
          r.final_output && typeof r.final_output === "string"
            ? r.final_output
            : "No output";
        if (r.generated_code && Object.keys(r.generated_code).length > 0) {
          finalOut += "\n\n### Generated Code:\n";
          for (const [filename, content] of Object.entries(
            r.generated_code as Record<string, string>
          )) {
            finalOut += `\n#### ${filename}\n\`\`\`python\n${content}\n\`\`\`\n`;
          }
        }
        setFinalReport(finalOut);
        setPhase("done");
        setStartedAt(null);
        break;
      }

      case "error": {
        setError(msg.message || "Unknown error");
        setPhase("error");
        setStartedAt(null);
        break;
      }
    }
  }, []);

  const triggerRun = useCallback(() => setRunId((n) => n + 1), []);

  const sendEscalationAnswer = useCallback(
    (escalation_id: string, answer: string) => {
      wsRef.current?.send(
        JSON.stringify({ type: "escalation_answer", escalation_id, answer })
      );
      setPendingReview(null);
    },
    []
  );

  const dismissReview = useCallback(() => {
    setPendingReview(null);
  }, []);

  return {
    terminalLines,
    codeLines,
    phase,
    finalReport,
    error,
    metrics,
    graphNodes,
    graphEdges,
    telemetry,
    criticVerdicts,
    retryStrategies,
    memoryActivity,
    pendingReview,
    liveCodeStream,
    triggerRun,
    sendEscalationAnswer,
    dismissReview,
    wsRef,
    startedAt,
  };
}
