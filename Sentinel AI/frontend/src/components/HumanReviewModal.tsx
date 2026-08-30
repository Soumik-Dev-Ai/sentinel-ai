import React, { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import type { NeedsHumanReview } from "../types/multiagent";

/* ============================================================================
   HumanReviewModal
   ----------------------------------------------------------------------------
   Triggered when the backend emits a `needs_human_review` event. Pauses
   execution by displaying a modal that requires the user to type an answer
   before the agent resumes. The answer is sent back over the WebSocket with
   `{"type": "escalation_answer", "escalation_id": ..., "answer": ...}`.
   ============================================================================ */

interface HumanReviewModalProps {
  review: NeedsHumanReview | null;
  onSubmit: (escalation_id: string, answer: string) => void;
  onDismiss: () => void;
}

export const HumanReviewModal: React.FC<HumanReviewModalProps> = ({
  review,
  onSubmit,
  onDismiss,
}) => {
  const [text, setText] = useState("");

  // Reset text whenever a new review target arrives.
  React.useEffect(() => {
    if (review) setText("");
  }, [review]);

  return (
    <AnimatePresence>
      {review && (
        <motion.div
          key={review.escalation_id}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.25 }}
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(0,0,0,0.65)",
            backdropFilter: "blur(6px)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 1000,
          }}
          onClick={onDismiss}
        >
          <motion.div
            initial={{ scale: 0.92, y: 20, opacity: 0 }}
            animate={{ scale: 1, y: 0, opacity: 1 }}
            exit={{ scale: 0.95, y: -10, opacity: 0 }}
            transition={{ type: "spring", stiffness: 220, damping: 22 }}
            onClick={(e) => e.stopPropagation()}
            style={{
              width: "min(560px, calc(100vw - 32px))",
              borderRadius: 16,
              padding: 22,
              background:
                "linear-gradient(180deg, rgba(40,18,55,0.95), rgba(20,18,28,0.96))",
              border: "1px solid rgba(180,120,255,0.35)",
              boxShadow: "0 0 40px rgba(124,58,237,0.45), 0 8px 32px rgba(0,0,0,0.4)",
              color: "white",
              fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
            }}
          >
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                marginBottom: 14,
              }}
            >
              <div
                style={{
                  width: 32,
                  height: 32,
                  borderRadius: 8,
                  background: "rgba(124,58,237,0.25)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                <svg
                  viewBox="0 0 24 24"
                  width={18}
                  height={18}
                  stroke="rgb(200,170,255)"
                  strokeWidth={2}
                  fill="none"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M12 2v2M12 20v2M4 12H2M22 12h-2M5.6 5.6l1.4 1.4M17 17l1.4 1.4M5.6 18.4L7 17M17 7l1.4-1.4" />
                  <circle cx="12" cy="12" r="3.5" />
                </svg>
              </div>
              <div>
                <div style={{ fontSize: 12, opacity: 0.65, textTransform: "uppercase", letterSpacing: 2 }}>
                  Human-in-the-loop
                </div>
                <div style={{ fontSize: 16, fontWeight: 600 }}>
                  Needs your review
                </div>
              </div>
            </div>

            <div
              style={{
                fontSize: 12,
                opacity: 0.7,
                marginBottom: 6,
              }}
            >
              Subtask: <span style={{ color: "rgb(220,200,255)" }}>{review.subtask_id}</span>
              <span style={{ marginLeft: 10 }}>
                Confidence: <span style={{ color: review.confidence < 0.5 ? "rgb(255,120,120)" : "rgb(120,220,140)" }}>
                  {(review.confidence * 100).toFixed(0)}%
                </span>
              </span>
            </div>

            <div
              style={{
                background: "rgba(0,0,0,0.32)",
                borderRadius: 10,
                padding: "12px 14px",
                border: "1px solid rgba(255,255,255,0.08)",
                fontSize: 13,
                lineHeight: 1.5,
                color: "rgba(255,255,255,0.92)",
                marginBottom: 14,
                whiteSpace: "pre-wrap",
              }}
            >
              {review.question}
            </div>

            {review.context_summary &&
              Object.keys(review.context_summary).length > 0 && (
                <details
                  style={{
                    marginBottom: 12,
                    fontSize: 11,
                    color: "rgba(255,255,255,0.6)",
                  }}
                >
                  <summary style={{ cursor: "pointer", opacity: 0.7 }}>
                    Context summary
                  </summary>
                  <pre
                    style={{
                      marginTop: 6,
                      padding: 8,
                      background: "rgba(0,0,0,0.25)",
                      borderRadius: 6,
                      overflow: "auto",
                      maxHeight: 180,
                      fontSize: 11,
                    }}
                  >
                    {JSON.stringify(review.context_summary, null, 2)}
                  </pre>
                </details>
              )}

            <textarea
              autoFocus
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Type your hint or clarification…  (Cmd/Ctrl + Enter to submit)"
              onKeyDown={(e) => {
                if ((e.metaKey || e.ctrlKey) && e.key === "Enter" && text.trim()) {
                  onSubmit(review.escalation_id, text.trim());
                }
              }}
              rows={4}
              style={{
                width: "100%",
                boxSizing: "border-box",
                background: "rgba(0,0,0,0.4)",
                border: "1px solid rgba(255,255,255,0.12)",
                color: "white",
                borderRadius: 8,
                padding: 10,
                fontFamily: "inherit",
                fontSize: 13,
                resize: "vertical",
                outline: "none",
              }}
            />

            <div
              style={{
                display: "flex",
                justifyContent: "flex-end",
                gap: 8,
                marginTop: 14,
              }}
            >
              <button
                onClick={onDismiss}
                style={{
                  background: "transparent",
                  color: "rgba(255,255,255,0.7)",
                  border: "1px solid rgba(255,255,255,0.1)",
                  borderRadius: 8,
                  padding: "8px 16px",
                  cursor: "pointer",
                  fontFamily: "inherit",
                  fontSize: 12,
                  textTransform: "uppercase",
                  letterSpacing: 1,
                }}
              >
                Dismiss
              </button>
              <button
                onClick={() => {
                  if (text.trim()) onSubmit(review.escalation_id, text.trim());
                }}
                disabled={!text.trim()}
                style={{
                  background: text.trim()
                    ? "linear-gradient(180deg, rgb(168,85,247), rgb(124,58,237))"
                    : "rgba(124,58,237,0.35)",
                  color: "white",
                  border: "none",
                  borderRadius: 8,
                  padding: "8px 18px",
                  cursor: text.trim() ? "pointer" : "not-allowed",
                  fontFamily: "inherit",
                  fontSize: 12,
                  textTransform: "uppercase",
                  letterSpacing: 1.5,
                  opacity: text.trim() ? 1 : 0.6,
                }}
              >
                Submit Hint
              </button>
            </div>
            <div
              style={{
                marginTop: 10,
                fontSize: 10,
                color: "rgba(255,255,255,0.45)",
                textAlign: "center",
              }}
            >
              ⏳ Auto-aborting in {Math.round(review.timeout_seconds)}s if unanswered
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
};
