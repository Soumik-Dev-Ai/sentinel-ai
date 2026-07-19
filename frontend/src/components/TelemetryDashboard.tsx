import React from "react";
import { motion, AnimatePresence } from "framer-motion";

import type { TelemetryUpdate, AgentName } from "../types/multiagent";

/* ============================================================================
   TelemetryDashboard
   ----------------------------------------------------------------------------
   Live tile grid showing token+cost telemetry emitted by the backend over
   the WebSocket (`telemetry_update` events). Shows:
     - Total tokens (I/O breakdown).
     - Total USD cost.
     - Per-agent consumed tokens + cost.
     - Budget remaining (tokens and USD).
   Falls back gracefully to 0s before the first telemetry tick arrives.
   ============================================================================ */

interface TelemetryDashboardProps {
  telemetry: TelemetryUpdate | null;
  /** Run start time used to compute tokens/sec rate. */
  startedAt: number | null;
  isRunning: boolean;
}

const AGENT_DOT: Record<AgentName, string> = {
  orchestrator: "#7c3aed",
  coder: "#3b82f6",
  critic: "#f59e0b",
  executor: "#10b981",
  agent: "#64748b",
};

const AGENT_LABEL: Record<AgentName, string> = {
  orchestrator: "Orchestrator",
  coder:       "Coder",
  critic:      "Critic",
  executor:    "Executor",
  agent:       "Agent",
};

/* --------- helpers --------- */

function usd(n: number): string {
  if (n >= 1) return `$${n.toFixed(2)}`;
  if (n >= 0.01) return `$${n.toFixed(3)}`;
  if (n >= 0.0001) return `$${n.toFixed(4)}`;
  return `$${n.toExponential(2)}`;
}

function fmtTok(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(2) + "M";
  if (n >= 1_000) return (n / 1000).toFixed(1) + "k";
  return String(n);
}

/* --------- tiles --------- */

const Tile: React.FC<{
  label: string;
  value: string;
  hint?: string;
  accent?: string;
  animateKey?: string | number;
}> = ({ label, value, hint, accent = "hsl(119 99% 60%)", animateKey }) => (
  <motion.div
    layout
    style={{
      padding: "12px 14px",
      borderRadius: 10,
      background: "rgba(255,255,255,0.03)",
      border: "1px solid rgba(255,255,255,0.07)",
      backdropFilter: "blur(8px)",
      position: "relative",
      overflow: "hidden",
    }}
  >
    <div
      style={{
        fontSize: 9,
        textTransform: "uppercase",
        letterSpacing: 2,
        color: "hsl(0 0% 60%)",
        marginBottom: 4,
      }}
    >
      {label}
    </div>
    <AnimatePresence mode="popLayout">
      <motion.div
        key={animateKey ?? value}
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -6 }}
        transition={{ duration: 0.18 }}
        style={{
          fontSize: 18,
          fontWeight: 600,
          color: accent,
          fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
        }}
      >
        {value}
      </motion.div>
    </AnimatePresence>
    {hint && (
      <div
        style={{
          fontSize: 10,
          color: "hsl(0 0% 50%)",
          marginTop: 4,
        }}
      >
        {hint}
      </div>
    )}
  </motion.div>
);

/* --------- main dashboard --------- */

export const TelemetryDashboard: React.FC<TelemetryDashboardProps> = ({
  telemetry,
  startedAt,
  isRunning,
}) => {
  const t = telemetry ?? ({} as TelemetryUpdate);
  const totalIn = t.total_input_tokens ?? 0;
  const totalOut = t.total_output_tokens ?? 0;
  const totalTokens = t.total_tokens ?? 0;
  const totalCost = t.total_cost_usd ?? 0;
  const calls = t.calls ?? 0;
  const remTok = t.budget_remaining_tokens ?? null;
  const remUsd = t.budget_remaining_usd ?? null;
  const exhausted = !!t.budget_exhausted;
  const elapsed = startedAt ? Math.max(0.1, (Date.now() - startedAt) / 1000) : 0;
  const tokensPerSec = elapsed > 0 && totalTokens > 0 ? totalTokens / elapsed : 0;

  const perAgentEntries = Object.entries(t.per_agent ?? {}).sort(
    (a, b) => (b[1].cost_usd + b[1].input_tokens + b[1].output_tokens) - (a[1].cost_usd + a[1].input_tokens + a[1].output_tokens)
  );

  return (
    <div
      style={{
        background: "rgba(8, 8, 12, 0.85)",
        borderRadius: 14,
        padding: 14,
        border: "1px solid rgba(255,255,255,0.07)",
        boxShadow: "0 4px 24px rgba(0,0,0,0.4)",
        fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: 10,
        }}
      >
        <span
          style={{
            fontSize: 10,
            textTransform: "uppercase",
            letterSpacing: 3,
            color: "hsl(0 0% 60%)",
          }}
        >
          Telemetry
        </span>
        <span
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 6,
            fontSize: 10,
            color: exhausted ? "hsl(0 84% 65%)" : "hsl(119 60% 70%)",
            textTransform: "uppercase",
            letterSpacing: 2,
          }}
        >
          <motion.span
            style={{
              width: 7,
              height: 7,
              borderRadius: "50%",
              background: exhausted ? "hsl(0 84% 65%)" : "hsl(119 60% 70%)",
            }}
            animate={isRunning && !exhausted ? { opacity: [1, 0.3, 1] } : { opacity: 1 }}
            transition={{ duration: 1.1, repeat: Infinity }}
          />
          {exhausted ? "Budget Exhausted" : isRunning ? "Live" : "Idle"}
        </span>
      </div>

      {/* main tile grid */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(4, 1fr)",
          gap: 8,
        }}
      >
        <Tile label="Input" value={fmtTok(totalIn)} hint="prompt tokens" accent="hsl(210 80% 65%)" />
        <Tile label="Output" value={fmtTok(totalOut)} hint="completion tokens" accent="hsl(45, 90%, 60%)" />
        <Tile
          label="Total"
          value={fmtTok(totalTokens)}
          hint={tokensPerSec > 0 ? `${tokensPerSec.toFixed(0)} tok/s` : "tokens"}
          accent="hsl(119, 60%, 60%)"
          animateKey={totalTokens}
        />
        <Tile label="Cost" value={usd(totalCost)} hint={`${calls} calls`} accent="hsl(280, 80%, 70%)" />
      </div>

      {/* budget remaining removed as requested */}

      {/* per-agent breakdown */}
      <div
        style={{
          marginTop: 10,
          paddingTop: 10,
          borderTop: "1px solid rgba(255,255,255,0.08)",
        }}
      >
        <div
          style={{
            fontSize: 9,
            textTransform: "uppercase",
            letterSpacing: 2,
            color: "hsl(0 0% 50%)",
            marginBottom: 6,
          }}
        >
          Per-Agent
        </div>
        {perAgentEntries.length === 0 ? (
          <div style={{ fontSize: 11, color: "hsl(0 0% 50%)" }}>
            No LLM calls yet.
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            {perAgentEntries.map(([agentName, stats]) => {
              const dotColor =
                AGENT_DOT[agentName as AgentName] ?? AGENT_DOT.agent;
              const label =
                AGENT_LABEL[agentName as AgentName] ?? agentName;
              const total = stats.input_tokens + stats.output_tokens;
              const maxTotal = Math.max(
                1,
                ...perAgentEntries.map(
                  ([, s]) => s.input_tokens + s.output_tokens
                )
              );
              const fill = (total / maxTotal) * 100;
              return (
                <motion.div
                  key={agentName}
                  layout
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ duration: 0.3 }}
                  style={{
                    display: "grid",
                    gridTemplateColumns: "90px 1fr 70px 70px",
                    alignItems: "center",
                    gap: 8,
                    fontSize: 10,
                  }}
                >
                  <span
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      gap: 6,
                      color: "hsl(0 0% 75%)",
                    }}
                  >
                    <span
                      style={{
                        width: 6,
                        height: 6,
                        borderRadius: "50%",
                        background: dotColor,
                      }}
                    />
                    {label}
                  </span>
                  <div
                    style={{
                      height: 6,
                      borderRadius: 3,
                      background: "rgba(255,255,255,0.05)",
                      overflow: "hidden",
                      position: "relative",
                    }}
                  >
                    <motion.div
                      initial={{ width: 0 }}
                      animate={{ width: `${fill}%` }}
                      transition={{ duration: 0.4 }}
                      style={{
                        position: "absolute",
                        inset: 0,
                        background: dotColor,
                        opacity: 0.85,
                      }}
                    />
                  </div>
                  <span style={{ color: "hsl(0 0% 70%)", textAlign: "right" }}>
                    {fmtTok(total)}
                  </span>
                  <span
                    style={{
                      color: dotColor,
                      textAlign: "right",
                      fontWeight: 500,
                    }}
                  >
                    {usd(stats.cost_usd)}
                  </span>
                </motion.div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};
