import React, { useState, useCallback } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { GlassIntro } from "./components/GlassIntro";
import { Navbar } from "./components/Navbar";
import { HeroSection } from "./components/HeroSection";
import { AgentWorkspace } from "./components/AgentWorkspace";
import { EvaluationLab } from "./components/EvaluationLab";
import { useAgentSocket } from "./hooks/useAgentSocket";

type AppPhase = "INTRO" | "MAIN" | "WORKSPACE";

const App: React.FC = () => {
  const [phase, setPhase] = useState<AppPhase>("INTRO");
  const [goal, setGoal] = useState("");
  const [inputText, setInputText] = useState("");
  const [showEvalLab, setShowEvalLab] = useState(false);

  const agentState = useAgentSocket(phase === "WORKSPACE" && !showEvalLab ? goal : "", inputText);

  const handleIntroStart = useCallback(() => {
    setPhase("MAIN");
  }, []);

  const handleStartProcess = useCallback((userGoal: string, input: string) => {
    setGoal(userGoal);
    setInputText(input);
    setPhase("WORKSPACE");
    agentState.triggerRun();
  }, [agentState.triggerRun]);

  if (showEvalLab) {
    return (
      <div className="min-h-screen" style={{ background: "hsl(var(--hero-bg))", overflow: "auto", position: "relative" }}>
        <EvaluationLab onExit={() => setShowEvalLab(false)} />
      </div>
    );
  }

  return (
    <div className="min-h-screen" style={{ background: "hsl(var(--hero-bg))", position: "relative" }}>
      
      {phase !== "INTRO" && (
        <button 
          onClick={() => setShowEvalLab(true)}
          style={{ position: "absolute", top: "20px", right: "20px", zIndex: 100, padding: "10px 20px", background: "transparent", color: "white", borderRadius: "8px", border: "1px solid rgba(255,255,255,0.3)", cursor: "pointer", fontWeight: "bold", backdropFilter: "blur(10px)" }}
        >
          Evaluation Lab
        </button>
      )}

      <AnimatePresence mode="sync">
        {phase === "INTRO" && (
          <motion.div key="intro" exit={{ opacity: 0 }} transition={{ duration: 0.4 }}>
            <GlassIntro onStart={handleIntroStart} />
          </motion.div>
        )}
        {phase === "MAIN" && (
          <motion.div
            key="main"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0, y: -30 }}
            transition={{ duration: 0.4 }}
          >
            <HeroSection onStartProcess={handleStartProcess} />
          </motion.div>
        )}
        {phase === "WORKSPACE" && (
          <motion.div
            key="workspace"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.5 }}
          >
            <AgentWorkspace
              goal={goal}
              inputText={inputText}
              terminalLines={agentState.terminalLines}
              codeLines={agentState.codeLines}
              liveCodeStream={agentState.liveCodeStream}
              phase={agentState.phase}
              finalReport={agentState.finalReport}
              error={agentState.error}
              metrics={agentState.metrics}
              graphNodes={agentState.graphNodes}
              graphEdges={agentState.graphEdges}
              telemetry={agentState.telemetry}
              pendingReview={agentState.pendingReview}
              startedAt={agentState.startedAt}
              onEscalationAnswer={agentState.sendEscalationAnswer}
              onDismissReview={agentState.dismissReview}
            />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

export default App;
