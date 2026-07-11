import React, { useEffect, useRef, useState, useCallback } from "react";
import { motion, AnimatePresence, LayoutGroup } from "framer-motion";
import ReactMarkdown from "react-markdown";
import type { TerminalLine, CodeLine } from "../services/agentBridge";
import type { AgentPhase } from "../hooks/useAgentSocket";

const SMOOTH_SPRING = { type: "spring" as const, stiffness: 100, damping: 22, mass: 0.8 };

/* =====================================================================
   TerminalBox — Shows agent logs (live or simulated)
   ===================================================================== */
const TerminalBox: React.FC<{ lines: TerminalLine[]; running: boolean }> = ({ lines, running }) => {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [lines]);

  const getColor = (type: string) => {
    switch (type) {
      case "command": return "hsl(var(--foreground))";
      case "info": return "hsl(var(--muted-foreground))";
      case "step": return "hsl(210, 80%, 65%)";
      case "action": return "hsl(45, 90%, 65%)";
      case "success": return "hsl(var(--primary))";
      case "error": return "hsl(0, 84%, 60%)";
      case "recovery": return "hsl(280, 80%, 65%)";
      case "done": return "hsl(var(--primary))";
      case "complete": return "hsl(var(--primary))";
      case "separator": return "hsl(var(--muted-foreground))";
      default: return "hsl(var(--muted-foreground))";
    }
  };

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center gap-2 px-2 py-3" style={{ borderBottom: "1px solid hsl(var(--border))" }}>
        <div className="flex gap-1.5">
          <div className="w-2.5 h-2.5 rounded-full bg-red-500/70" />
          <div className="w-2.5 h-2.5 rounded-full bg-yellow-500/70" />
          <div className="w-2.5 h-2.5 rounded-full bg-green-500/70" />
        </div>
        <span className="text-[10px] uppercase tracking-widest text-[hsl(var(--muted-foreground))] ml-2">Live Terminal</span>
        {running && (
          <motion.div className="ml-auto w-2 h-2 rounded-full bg-[hsl(var(--primary))]" animate={{ opacity: [1, 0.3, 1] }} transition={{ duration: 1.2, repeat: Infinity }} />
        )}
      </div>
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-2 py-4 terminal-text" style={{ background: "hsl(0, 0%, 6%)" }}>
        {lines.map((line, idx) => (
          <motion.div
            key={idx}
            initial={{ opacity: 0, x: -8 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.3 }}
            style={{ color: getColor(line.type) }}
            className="py-0.5"
          >
            {line.text}
          </motion.div>
        ))}
        {running && <span className="terminal-cursor" />}
      </div>
    </div>
  );
};

/* =====================================================================
   CodeBox — Shows generated code
   ===================================================================== */
const CodeBox: React.FC<{ lines: CodeLine[]; running: boolean }> = ({ lines, running }) => {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [lines]);

  const getStyle = (type: string): React.CSSProperties => {
    switch (type) {
      case "comment": return { color: "hsl(var(--muted-foreground))", fontStyle: "italic" };
      case "code": return { color: "hsl(var(--foreground))" };
      case "error": return { color: "hsl(0, 84%, 60%)", textDecoration: "line-through", opacity: 0.6 };
      case "recovery": return { color: "hsl(280, 80%, 65%)", fontStyle: "italic" };
      case "fix": return { color: "hsl(var(--primary))", fontWeight: 600 };
      case "success": return { color: "hsl(var(--primary))", fontWeight: 600 };
      default: return { color: "hsl(var(--muted-foreground))" };
    }
  };

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center gap-2 px-2 py-3" style={{ borderBottom: "1px solid hsl(var(--border))" }}>
        <div className="flex gap-1.5">
          <div className="w-2.5 h-2.5 rounded-full bg-red-500/70" />
          <div className="w-2.5 h-2.5 rounded-full bg-yellow-500/70" />
          <div className="w-2.5 h-2.5 rounded-full bg-green-500/70" />
        </div>
        <span className="text-[10px] uppercase tracking-widest text-[hsl(var(--muted-foreground))] ml-2">Code Generation</span>
        {running && (
          <motion.div className="ml-auto w-2 h-2 rounded-full bg-[hsl(var(--primary))]" animate={{ opacity: [1, 0.3, 1] }} transition={{ duration: 1.2, repeat: Infinity }} />
        )}
      </div>
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-2 py-4 terminal-text" style={{ background: "hsl(0, 0%, 6%)" }}>
        {lines.map((line, idx) => (
          <motion.div
            key={idx}
            initial={{ opacity: 0, x: -8 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.3 }}
            style={getStyle(line.type)}
            className="py-0.5"
          >
            {line.text || "\u00A0"}
          </motion.div>
        ))}
        {running && <span className="terminal-cursor" />}
      </div>
    </div>
  );
};

/* =====================================================================
   FinalContent — Typewriter final output
   ===================================================================== */
const FinalContent: React.FC<{ report: string }> = ({ report }) => {
  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center gap-2 px-2 py-3" style={{ borderBottom: "1px solid hsla(119, 99%, 46%, 0.15)" }}>
        <div className="flex gap-1.5">
          <div className="w-2.5 h-2.5 rounded-full" style={{ background: "hsl(var(--primary))", opacity: 0.7 }} />
          <div className="w-2.5 h-2.5 rounded-full" style={{ background: "hsl(var(--primary))", opacity: 0.4 }} />
          <div className="w-2.5 h-2.5 rounded-full" style={{ background: "hsl(var(--primary))", opacity: 0.2 }} />
        </div>
        <span className="text-[10px] uppercase tracking-widest text-[hsl(var(--primary))] ml-2 font-medium">Agent Report — Complete</span>
      </div>
      <div className="flex-1 overflow-y-auto px-4 py-6 md:px-6 md:py-8" style={{ background: "hsl(0, 0%, 5%)" }}>
        <div className="space-y-4 text-sm text-[hsl(var(--foreground))] font-light leading-relaxed">
          {report.split("\n").map((para, i) => {
            if (para.startsWith("####") || para.startsWith("###")) {
              return <h3 key={i} className="text-lg text-[hsl(var(--primary))] font-semibold mt-4 mb-2">{para.replace(/#/g, "").trim()}</h3>;
            }
            if (para.startsWith("```")) return null;
            if (para.startsWith("def ") || para.startsWith("    ") || para.startsWith("class ") || para.startsWith("import ") || para.startsWith("from ")) {
              return <pre key={i} className="terminal-text px-4 py-1" style={{ color: "hsl(var(--foreground))", margin: 0 }}>{para}</pre>;
            }
            return <p key={i}>{para}</p>;
          })}
        </div>
      </div>
    </div>
  );
};

/* =====================================================================
   AgentWorkspace — full lifecycle driven by hook state
   ===================================================================== */
type WorkPhase = "RUNNING" | "DONE" | "MERGED";

interface AgentWorkspaceProps {
  goal: string;
  inputText?: string;
  terminalLines: TerminalLine[];
  codeLines: CodeLine[];
  phase: AgentPhase;
  finalReport: string;
  error: string | null;
  metrics: Record<string, number>;
}

export const AgentWorkspace: React.FC<AgentWorkspaceProps> = ({
  goal, terminalLines, codeLines, phase: agentPhase, finalReport, error, metrics,
}) => {
  const [workPhase, setWorkPhase] = useState<WorkPhase>("RUNNING");

  useEffect(() => {
    if (agentPhase === "done") {
      const t = setTimeout(() => setWorkPhase("DONE"), 500);
      return () => clearTimeout(t);
    }
    if (agentPhase === "error") {
      setWorkPhase("DONE");
    }
  }, [agentPhase]);

  useEffect(() => {
    setWorkPhase("RUNNING");
  }, [goal]);

  const handleShowFinal = useCallback(() => {
    setWorkPhase("MERGED");
  }, []);

  const isMerged = workPhase === "MERGED";
  const isDone = workPhase === "DONE" || isMerged;
  const running = agentPhase === "running";

  return (
    <motion.div
      className="w-full min-h-screen flex flex-col items-center justify-center px-4 py-24"
      style={{ background: "hsl(var(--hero-bg))" }}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.5 }}
    >
      {error && (
        <motion.div
          className="mb-4 px-6 py-3 rounded-xl text-sm"
          style={{ background: "hsla(0, 84%, 30%, 0.3)", color: "hsl(0, 84%, 70%)", border: "1px solid hsla(0, 84%, 50%, 0.3)" }}
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
        >
          {error}
        </motion.div>
      )}

      <motion.div className="mb-6 text-center" initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}>
        <p className="text-[10px] uppercase tracking-widest text-[hsl(var(--muted-foreground))] mb-1">
          {isMerged ? "Final Report" : "Processing Goal"}
        </p>
        <p className="text-sm text-[hsl(var(--foreground))] font-light max-w-lg truncate">"{goal}"</p>
      </motion.div>

      <LayoutGroup>
        <motion.div layout className="w-full" style={{ maxWidth: isMerged ? "48rem" : "72rem" }} transition={SMOOTH_SPRING}>
          <motion.div layout className={`grid gap-4 ${isMerged ? "grid-cols-1" : "grid-cols-1 lg:grid-cols-2"}`} transition={SMOOTH_SPRING}>
            {!isMerged && (
              <motion.div
                layout layoutId="box-left"
                className="glass rounded-2xl overflow-hidden h-[420px] md:h-[500px]"
                initial={{ opacity: 0, x: -60, scale: 0.92 }}
                animate={{ opacity: 1, x: 0, scale: 1 }}
                exit={{ opacity: 0, x: -30, scale: 0.95, filter: "blur(8px)", transition: { duration: 0.5, ease: [0.4, 0, 0.2, 1] } }}
                transition={{ duration: 0.7, ease: [0.16, 1, 0.3, 1], delay: 0.3, layout: SMOOTH_SPRING }}
              >
                <TerminalBox lines={terminalLines} running={running} />
              </motion.div>
            )}
            {!isMerged && (
              <motion.div
                layout layoutId="box-right"
                className="glass rounded-2xl overflow-hidden h-[420px] md:h-[500px]"
                initial={{ opacity: 0, x: 60, scale: 0.92 }}
                animate={{ opacity: 1, x: 0, scale: 1 }}
                exit={{ opacity: 0, x: 30, scale: 0.95, filter: "blur(8px)", transition: { duration: 0.5, ease: [0.4, 0, 0.2, 1] } }}
                transition={{ duration: 0.7, ease: [0.16, 1, 0.3, 1], delay: 0.4, layout: SMOOTH_SPRING }}
              >
                <CodeBox lines={codeLines} running={running} />
              </motion.div>
            )}
            {isMerged && (
              <motion.div
                layout layoutId="box-merged"
                className="glass-green rounded-2xl overflow-hidden h-[500px] md:h-[560px] animate-pulse-glow"
                initial={{ opacity: 0, scale: 0.92, y: 20 }}
                animate={{ opacity: 1, scale: 1, y: 0 }}
                transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1], delay: 0.15, layout: SMOOTH_SPRING }}
              >
                <FinalContent report={finalReport} />
              </motion.div>
            )}
          </motion.div>
        </motion.div>
      </LayoutGroup>

      <motion.div className="mt-8 flex flex-col items-center gap-4" layout transition={SMOOTH_SPRING}>
        <AnimatePresence mode="wait">
          {workPhase === "RUNNING" && (
            <motion.div key="running" className="flex items-center gap-3" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0, y: -10 }} transition={{ duration: 0.3 }}>
              <motion.div className="w-2 h-2 rounded-full bg-[hsl(var(--primary))]" animate={{ opacity: [1, 0.3, 1] }} transition={{ duration: 1, repeat: Infinity }} />
              <span className="text-xs text-[hsl(var(--muted-foreground))] uppercase tracking-widest">
                {agentPhase === "idle" ? "Connecting..." : "Agent Processing..."}
              </span>
            </motion.div>
          )}
          {workPhase === "DONE" && (
            <motion.div key="done" className="flex flex-col items-center gap-4" initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}>
              <div className="flex items-center gap-3">
                <motion.div className="w-6 h-6 rounded-full flex items-center justify-center" style={{ background: "hsla(119, 99%, 46%, 0.15)" }} initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ type: "spring", stiffness: 300, damping: 15, delay: 0.2 }}>
                  <svg viewBox="0 0 24 24" fill="none" className="w-3.5 h-3.5" stroke="hsl(var(--primary))" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M5 13l4 4L19 7" />
                  </svg>
                </motion.div>
                <span className="text-xs text-[hsl(var(--primary))] uppercase tracking-widest font-medium">
                  Process Finished
                </span>
              </div>
              {metrics.steps > 0 && (
                <div className="flex gap-4 text-[10px] text-[hsl(var(--muted-foreground))] uppercase tracking-widest">
                  <span>Steps: {metrics.steps}</span>
                  <span>Corrections: {metrics.selfCorrections}</span>
                  <span>Switches: {metrics.providerSwitches}</span>
                </div>
              )}
              <motion.button
                onClick={handleShowFinal}
                className="px-8 py-3.5 rounded-xl text-sm font-semibold uppercase tracking-widest cursor-pointer transition-all active:scale-[0.96]"
                style={{ background: "hsl(var(--primary))", color: "hsl(var(--primary-foreground))" }}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.4, duration: 0.5 }}
                whileHover={{ scale: 1.03 }}
                whileTap={{ scale: 0.97 }}
              >
                Show the Final Output
              </motion.button>
              <motion.p className="text-[10px] text-[hsl(var(--muted-foreground))] tracking-widest uppercase" initial={{ opacity: 0 }} animate={{ opacity: 0.5 }} transition={{ delay: 0.7 }}>
                The two panels will merge into the report
              </motion.p>
            </motion.div>
          )}
          {workPhase === "MERGED" && (
            <motion.div key="merged" className="flex items-center gap-2" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.6, duration: 0.4 }}>
              <div className="w-2 h-2 rounded-full bg-[hsl(var(--primary))]" />
              <span className="text-[10px] uppercase tracking-widest text-[hsl(var(--muted-foreground))]">Sentinel AI • Self-Correcting Agent</span>
            </motion.div>
          )}
        </AnimatePresence>
      </motion.div>
    </motion.div>
  );
};
