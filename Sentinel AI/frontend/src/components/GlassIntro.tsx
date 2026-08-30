import React from "react";
import { motion } from "framer-motion";

interface GlassIntroProps {
  onStart: () => void;
}

export const GlassIntro: React.FC<GlassIntroProps> = ({ onStart }) => {
  return (
    <motion.section
      className="fixed inset-0 z-[100] flex items-center justify-center"
      style={{ background: "hsl(var(--hero-bg))" }}
      exit={{ opacity: 0, scale: 1.1 }}
      transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
    >
      {/* Animated background grid */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        {/* Radial glow */}
        <div
          className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] rounded-full opacity-20"
          style={{
            background:
              "radial-gradient(circle, hsla(119, 99%, 46%, 0.3) 0%, transparent 70%)",
          }}
        />
        {/* Grid lines */}
        <div
          className="absolute inset-0 opacity-[0.04]"
          style={{
            backgroundImage: `
              linear-gradient(hsla(0,0%,100%,0.3) 1px, transparent 1px),
              linear-gradient(90deg, hsla(0,0%,100%,0.3) 1px, transparent 1px)
            `,
            backgroundSize: "60px 60px",
          }}
        />
        {/* Scan line effect */}
        <motion.div
          className="absolute left-0 right-0 h-px opacity-10"
          style={{
            background:
              "linear-gradient(90deg, transparent, hsl(var(--primary)), transparent)",
          }}
          animate={{ top: ["-5%", "105%"] }}
          transition={{ duration: 4, ease: "linear", repeat: Infinity }}
        />
      </div>

      {/* Main glass card */}
      <motion.div
        className="relative glass-strong rounded-3xl px-2 py-12 md:px-2 md:py-16 flex flex-col items-center gap-8 max-w-lg mx-4"
        initial={{ opacity: 0, y: 40, scale: 0.9 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.9, ease: [0.16, 1, 0.3, 1], delay: 0.2 }}
      >
        {/* Shield icon */}
        <motion.div
          className="w-20 h-20 rounded-2xl flex items-center justify-center glass-green"
          initial={{ scale: 0, rotate: -180 }}
          animate={{ scale: 1, rotate: 0 }}
          transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1], delay: 0.5 }}
        >
          <svg
            viewBox="0 0 24 24"
            fill="none"
            className="w-10 h-10"
            stroke="hsl(var(--primary))"
            strokeWidth="1.5"
          >
            <path d="M12 2L3 7v5c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V7l-9-5z" />
            <path d="M9 12l2 2 4-4" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </motion.div>

        {/* Title */}
        <motion.div
          className="text-center"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.7, duration: 0.6 }}
        >
          <h1 className="text-3xl md:text-4xl font-bold tracking-tight text-[hsl(var(--foreground))] uppercase">
            Sentinel{" "}
            <span className="text-[hsl(var(--primary))]">AI</span>
          </h1>
          <p className="mt-3 text-sm text-[hsl(var(--muted-foreground))] font-light tracking-wide">
            Self-Correcting Multi-Step Agent
          </p>
        </motion.div>

        {/* Decorative dots */}
        <motion.div
          className="flex items-center gap-2"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.9, duration: 0.5 }}
        >
          {[0, 1, 2].map((i) => (
            <motion.div
              key={i}
              className="w-1.5 h-1.5 rounded-full bg-[hsl(var(--primary))]"
              animate={{ opacity: [0.3, 1, 0.3] }}
              transition={{
                duration: 1.5,
                repeat: Infinity,
                delay: i * 0.3,
              }}
            />
          ))}
        </motion.div>

        {/* Start button */}
        <motion.button
          onClick={onStart}
          className="relative group px-10 py-4 rounded-xl text-sm font-semibold uppercase tracking-widest cursor-pointer transition-all active:scale-[0.96]"
          style={{
            background: "hsl(var(--primary))",
            color: "hsl(var(--primary-foreground))",
          }}
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 1.1, duration: 0.6 }}
          whileHover={{ scale: 1.03 }}
          whileTap={{ scale: 0.97 }}
        >
          {/* Glow ring behind button */}
          <span className="absolute inset-0 rounded-xl opacity-0 group-hover:opacity-100 transition-opacity duration-500 pointer-events-none"
            style={{
              boxShadow: "0 0 30px hsla(119, 99%, 46%, 0.4), 0 0 60px hsla(119, 99%, 46%, 0.15)",
            }}
          />
          Start
        </motion.button>

        {/* Bottom text */}
        <motion.p
          className="text-[10px] text-[hsl(var(--muted-foreground))] font-light tracking-wider opacity-60"
          initial={{ opacity: 0 }}
          animate={{ opacity: 0.6 }}
          transition={{ delay: 1.3, duration: 0.5 }}
        >
          POWERED BY MULTI-LLM FALLBACK CHAIN
        </motion.p>
      </motion.div>
    </motion.section>
  );
};
