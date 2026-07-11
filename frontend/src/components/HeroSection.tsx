import React, { Suspense, useState } from "react";
import { motion } from "framer-motion";

const Spline = React.lazy(() => import("@splinetool/react-spline"));

interface HeroSectionProps {
  onStartProcess: (goal: string, input: string) => void;
}

export const HeroSection: React.FC<HeroSectionProps> = ({ onStartProcess }) => {
  const [input, setInput] = useState("");
  const [goal, setGoal] = useState("");

  const isReady = input.trim().length > 0 && goal.trim().length > 0;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (isReady) {
      onStartProcess(goal.trim(), input.trim());
    }
  };

  return (
    <section
      className="relative min-h-screen flex items-center justify-center overflow-hidden"
      style={{ background: "hsl(var(--hero-bg))" }}
    >
      {/* Spline 3D background */}
      <div className="absolute inset-0">
        <Suspense
          fallback={
            <div className="absolute inset-0" style={{ background: "hsl(var(--hero-bg))" }} />
          }
        >
          <Spline
            scene="https://prod.spline.design/Slk6b8kz3LRlKiyk/scene.splinecode"
            className="w-full h-full"
          />
        </Suspense>
      </div>

      {/* Dark overlay */}
      <div className="absolute inset-0 bg-black/30 z-[1] pointer-events-none" />

      {/* Centered content */}
      <div className="relative z-10 w-full flex flex-col items-center justify-center px-4">
        {/* Title */}
        <motion.h1
          className="text-[clamp(2.5rem,7vw,5rem)] font-bold leading-[1.05] tracking-[-0.05em] text-[hsl(var(--foreground))] uppercase text-center mb-3"
          initial={{ opacity: 0, y: 20, filter: "blur(4px)" }}
          animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
          transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1], delay: 0.1 }}
        >
          Sentinel <span className="text-[hsl(var(--primary))]">AI</span>
        </motion.h1>

        {/* Subtitle */}
        <motion.p
          className="text-[hsl(var(--foreground))]/80 text-[clamp(0.9rem,2vw,1.4rem)] font-light mb-12 text-center max-w-md"
          initial={{ opacity: 0, y: 20, filter: "blur(4px)" }}
          animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
          transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1], delay: 0.2 }}
        >
          Self-correcting multi-step agent for code generation
        </motion.p>

        {/* Glass input card — centered, medium size */}
        <motion.div
          className="glass-strong rounded-2xl px-6 py-6 md:px-6 md:py-8 w-full max-w-[29rem] pointer-events-auto"
          initial={{ opacity: 0, y: 30, scale: 0.95 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1], delay: 0.3 }}
        >
          <form onSubmit={handleSubmit} className="flex flex-col gap-0">

            {/* ── Section 1: Input ── */}
            <div className="flex flex-col gap-2.5">
              <label className="text-xs uppercase tracking-widest text-[hsl(var(--muted-foreground))] font-medium flex items-center gap-2">
                <span
                  className="w-5 h-5 rounded-md flex items-center justify-center text-[10px] font-bold"
                  style={{
                    background: "hsl(var(--primary))",
                    color: "hsl(var(--primary-foreground))",
                  }}
                >
                  1
                </span>
                Provide your input
              </label>
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="e.g. Paste code, data, or context the agent should work with..."
                className="w-full bg-[hsl(var(--hero-bg))] text-[hsl(var(--foreground))] placeholder:text-[hsl(var(--muted-foreground))]/40 text-sm font-light rounded-xl p-4 resize-none focus:outline-none focus:ring-2 focus:ring-[hsl(var(--primary))]/30 transition-all border-[10px] border-[hsl(var(--border))]"
                rows={3}
              />
            </div>

            {/* ── Divider ── */}
            <div className="flex items-center gap-3 my-6">
              <div className="flex-1 h-[2px]" style={{ background: "hsl(var(--border))" }} />
              <span className="text-[9px] uppercase tracking-[0.2em] text-[hsl(var(--muted-foreground))]/50 font-medium">
                then
              </span>
              <div className="flex-1 h-[2px]" style={{ background: "hsl(var(--border))" }} />
            </div>

            {/* ── Section 2: Goal ── */}
            <div className="flex flex-col gap-2.5">
              <label className="text-xs uppercase tracking-widest text-[hsl(var(--muted-foreground))] font-medium flex items-center gap-2">
                <span
                  className="w-5 h-5 rounded-md flex items-center justify-center text-[10px] font-bold"
                  style={{
                    background: "hsl(var(--primary))",
                    color: "hsl(var(--primary-foreground))",
                  }}
                >
                  2
                </span>
                Define your goal
              </label>
              <textarea
                value={goal}
                onChange={(e) => setGoal(e.target.value)}
                placeholder="e.g. Write a recursive Fibonacci function with unit tests..."
                className="w-full bg-[hsl(var(--hero-bg))] text-[hsl(var(--foreground))] placeholder:text-[hsl(var(--muted-foreground))]/40 text-sm font-light rounded-xl p-4 resize-none focus:outline-none focus:ring-2 focus:ring-[hsl(var(--primary))]/30 transition-all border-[10px] border-[hsl(var(--border))]"
                rows={3}
              />
            </div>

            {/* ── Start button ── */}
            <motion.button
              type="submit"
              disabled={!isReady}
              className="w-full py-3.5 rounded-xl text-sm font-semibold uppercase tracking-widest cursor-pointer transition-all active:scale-[0.97] disabled:opacity-40 disabled:cursor-not-allowed mt-5"
              style={{
                background: isReady
                  ? "hsl(var(--primary))"
                  : "hsl(var(--muted))",
                color: isReady
                  ? "hsl(var(--primary-foreground))"
                  : "hsl(var(--muted-foreground))",
              }}
              whileHover={isReady ? { scale: 1.02 } : {}}
              whileTap={isReady ? { scale: 0.97 } : {}}
            >
              Start the Process
            </motion.button>
          </form>

          {/* Trust line */}
          <p className="text-[hsl(var(--muted-foreground))]/50 text-[10px] font-light mt-4 text-center tracking-wider">
            Multi-LLM fallback • Self-correcting • Budget-aware recovery
          </p>
        </motion.div>
      </div>
    </section>
  );
};
