/** Shared types for Sentinel AI 2.0 multi-agent events. */

export type AgentName = "orchestrator" | "coder" | "critic" | "executor" | "agent";

export type NodeStatus =
  | "active"      // currently running
  | "pending"     // queued, not yet started
  | "candidate"  // ToT candidate path (orchestrator)
  | "selected"     // chosen by ToT
  | "rejected"     // not chosen
  | "success"      // succeeded
  | "error"        // crashed or failed
  | "rejected";   // critiqued / failed code

/** A node in the execution-graph. Mirrors backend `graph_node` events. */
export interface GraphNode {
  id: string;
  label: string;
  agent: AgentName;
  status: NodeStatus;
  /** Optional parent id (drives edge creation). */
  parent?: string;
  meta?: Record<string, unknown>;
  ts?: number;
}

/** An edge in the execution-graph. Mirrors backend `graph_edge` events. */
export interface GraphEdgeFE {
  id: string;
  source: string;
  target: string;
  animated?: boolean;
}

/** Critic verdict payload from `critic_verdict` event. */
export interface CriticVerdict {
  filename: string;
  passes: boolean;
  verdict: "ACCEPT" | "REJECT";
  scores: {
    correctness: number;
    edge_cases: number;
    acceptance: number;
    readability: number;
    total: number;
  };
  issues: string[];
  fix_suggestions: string[];
}

/** Telemetry tick from `telemetry_update` events. */
export interface TelemetryUpdate {
  total_input_tokens: number;
  total_output_tokens: number;
  total_tokens: number;
  total_cost_usd: number;
  per_agent: Record<string, {
    input_tokens: number;
    output_tokens: number;
    cost_usd: number;
    calls: number;
  }>;
  budget_remaining_tokens: number | null;
  budget_remaining_usd: number | null;
  budget_exhausted: boolean;
  budget_reason: string;
  calls: number;
}

/** Inbound `needs_human_review` event payload. */
export interface NeedsHumanReview {
  escalation_id: string;
  subtask_id: string;
  question: string;
  confidence: number;
  context_summary: Record<string, unknown>;
  timeout_seconds: number;
}

/** Retry chosen by router. */
export interface RetryStrategyEvent {
  subtask_id: string;
  category: "syntax" | "logic" | "external" | "unknown";
  exception: string;
  strategy: "line_patch" | "full_rewrite" | "backoff" | "none";
  attempt: number;
  wait_seconds: number;
  guidance: string;
}

/** MemoryActivity — when memories are stored or recalled. */
export interface MemoryActivity {
  kind: "solved" | "error";
  subtask_id?: string;
  filename?: string;
  query?: string;
  n?: number;
}
