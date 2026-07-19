import React, { useCallback, useEffect, useMemo, useRef } from "react";
import ReactFlow, {
  Background,
  Controls,
  useNodesState,
  useEdgesState,
  type Edge as RFEdge,
  type Node as RFNode,
  type NodeProps,
  Handle,
  Position,
  useReactFlow,
} from "reactflow";
import "reactflow/dist/style.css";

import type { GraphNode, GraphEdgeFE, NodeStatus, AgentName } from "../types/multiagent";

/* ============================================================================
   ExecutionGraph
   ----------------------------------------------------------------------------
   Live flowchart of the multi-agent pipeline. Consumes graph_node / graph_edge
   events pushed by the backend over WebSocket. Nodes auto-position based on
   row + column derived from the parent chain. Edges draw the agent-to-agent
   correction loop (e.g. Coder -> Critic -> Coder).
   ============================================================================ */

interface ExecutionGraphProps {
  nodes: GraphNode[];
  edges: GraphEdgeFE[];
  width?: number | string;
  height?: number | string;
  isRunning: boolean;
}

/* ---- visual config ---- */

const AGENT_COLOR: Record<AgentName, string> = {
  orchestrator: "#7c3aed",
  coder:       "#3b82f6",
  critic:      "#f59e0b",
  executor:    "#10b981",
  agent:       "#64748b",
};

const STATUS_GLOW: Record<NodeStatus, string> = {
  active:    "0 0 16px rgba(255,255,255,0.7)",
  pending:   "0 0 4px rgba(255,255,255,0.1)",
  candidate: "0 0 4px rgba(124,58,237,0.25)",
  selected:  "0 0 16px rgba(16,185,129,0.65)",
  rejected:  "0 0 6px rgba(244,63,94,0.4)",
  success:   "0 0 18px rgba(16,185,129,0.85)",
  error:     "0 0 18px rgba(244,63,94,0.85)",
};

const STATUS_BG: Record<NodeStatus, string> = {
  active:    "rgba(59,130,246,0.18)",
  pending:   "rgba(100,116,139,0.10)",
  candidate: "rgba(124,58,237,0.12)",
  selected:  "rgba(16,185,129,0.18)",
  rejected:  "rgba(244,63,94,0.15)",
  success:   "rgba(16,185,129,0.25)",
  error:     "rgba(244,63,94,0.22)",
};

const STATUS_BORDER: Record<NodeStatus, string> = {
  active:    "1px solid rgba(59,130,246,0.6)",
  candidate: "1px dashed rgba(124,58,237,0.45)",
  pending:   "1px solid rgba(100,116,139,0.4)",
  selected:  "1px solid rgba(16,185,129,0.65)",
  rejected:  "1px solid rgba(244,63,94,0.45)",
  success:   "1px solid rgba(16,185,129,0.85)",
  error:     "1px solid rgba(244,63,94,0.85)",
};

const LAYOUT_COL_W = 240;
const LAYOUT_ROW_H = 110;

/* ----------------------------------------------------------------------------
   Custom node renderer
   ---------------------------------------------------------------------------- */

interface AgentNodeData {
  label: string;
  agent: AgentName;
  status: NodeStatus;
  meta?: Record<string, unknown>;
}

const AgentNode: React.FC<NodeProps<AgentNodeData>> = ({ data, selected }) => {
  const color = AGENT_COLOR[data.agent || "agent"] || AGENT_COLOR.agent;
  const ring = STATUS_GLOW[data.status || "pending"] || STATUS_GLOW.pending;
  const bg = STATUS_BG[data.status || "pending"] || STATUS_BG.pending;
  const border = STATUS_BORDER[data.status || "pending"] || STATUS_BORDER.pending;

  const isFinalState = data.status === "success" || data.status === "error";

  return (
    <div
      style={{
        position: "relative",
        padding: "10px 14px",
        borderRadius: 12,
        background: bg,
        border,
        boxShadow: ring,
        backdropFilter: "blur(4px)",
        minWidth: 140,
        maxWidth: 220,
        color: "white",
        fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
        fontSize: 11,
        textAlign: "left",
        cursor: "default",
        transform: selected ? "scale(1.04)" : "scale(1)",
        transition: "all 0.25s cubic-bezier(0.4, 0, 0.2, 1)",
      }}
    >
      <Handle type="target" position={Position.Top} style={{ opacity: 0 }} />
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 6,
          marginBottom: 4,
        }}
      >
        <span
          style={{
            width: 8,
            height: 8,
            borderRadius: "50%",
            background: color,
            boxShadow: isFinalState ? "0 0 6px " + color : "none",
            animation:
              data.status === "active" ? "pulse 1s ease-in-out infinite" : "none",
          }}
        />
        <span style={{ opacity: 0.6, textTransform: "uppercase", fontSize: 9, letterSpacing: 1 }}>
          {data.agent}
        </span>
      </div>
      <div style={{ fontWeight: 500, whiteSpace: "pre-wrap", lineHeight: 1.25 }}>
        {data.label}
      </div>
      {data.meta && (data.meta as any).total != null && (
        <div style={{ marginTop: 4, fontSize: 9, opacity: 0.7 }}>
          score: {String((data.meta as any).total)}/100
        </div>
      )}
      {data.meta && (data.meta as any).conf != null && (
        <div style={{ marginTop: 4, fontSize: 9, opacity: 0.7 }}>
          conf: {Number((data.meta as any).conf).toFixed(2)}
        </div>
      )}
      <Handle type="source" position={Position.Bottom} style={{ opacity: 0 }} />
    </div>
  );
};

// Removed module-level nodeTypes to memoize it inside the component instead

/* ----------------------------------------------------------------------------
   Layout algorithm (deterministic)
   ----------------------------------------------------------------------------
   Top-down layered layout. The orchestrator is the root at row 0.
   ToT path candidates share row 1; subtasks row 2; per-attempt coder/critic/
   executor nodes form rows 3+ chained by parent ids.
   ---------------------------------------------------------------------------- */

function computeLayout(nodes: GraphNode[]): RFNode[] {
  const byId = new Map<string, GraphNode>();
  for (const n of nodes) byId.set(n.id, n);

  // Calculate row by walking parent chain.
  const rowCache = new Map<string, number>();
  const getRow = (id: string): number => {
    if (rowCache.has(id)) return rowCache.get(id)!;
    const node = byId.get(id);
    if (!node || !node.parent) {
      rowCache.set(id, 0);
      return 0;
    }
    const r = getRow(node.parent) + 1;
    rowCache.set(id, r);
    return r;
  };

  const rowsMap = new Map<number, GraphNode[]>();
  for (const n of nodes) {
    const r = getRow(n.id);
    if (!rowsMap.has(r)) rowsMap.set(r, []);
    rowsMap.get(r)!.push(n);
  }

  const rfNodes: RFNode[] = [];
  rowsMap.forEach((rowNodes, row) => {
    const total = rowNodes.length;
    const startX = -(total - 1) * LAYOUT_COL_W / 2;
    rowNodes.forEach((node, i) => {
      rfNodes.push({
        id: node.id,
        type: "agent",
        position: { x: startX + i * LAYOUT_COL_W, y: row * LAYOUT_ROW_H },
        data: {
          label: node.label,
          agent: node.agent,
          status: node.status,
          meta: node.meta,
        },
      });
    });
  });

  return rfNodes;
}

const AutoFit: React.FC<{ nodeCount: number }> = ({ nodeCount }) => {
  const { fitView, setCenter } = useReactFlow();
  
  useEffect(() => {
    // We use a slight delay so ReactFlow has time to render and measure the DOM elements for the new nodes.
    const t = setTimeout(() => {
      if (nodeCount === 1) {
        setCenter(100, 40, { zoom: 1.2, duration: 800 });
      } else if (nodeCount > 1) {
        fitView({ padding: 0.2, duration: 800 });
      }
    }, 50);
    return () => clearTimeout(t);
  }, [nodeCount, fitView, setCenter]);
  
  return null;
};

/* ----------------------------------------------------------------------------
   ExecutionGraph component
   ---------------------------------------------------------------------------- */

export const ExecutionGraph: React.FC<ExecutionGraphProps> = ({
  nodes,
  edges,
  width = "100%",
  height = 360,
  isRunning,
}) => {
  const [rfNodes, setRfNodes, onNodesChange] = useNodesState<RFNode[]>([]);
  const [rfEdges, setRfEdges, onEdgesChange] = useEdgesState<RFEdge[]>([]);
  const insertionOrderRef = useRef<string[]>([]);

  /* ---- update node state on prop changes ---- */
  useEffect(() => {
    // Track insertion order so previously-rendered nodes don't jump around.
    for (const n of nodes) {
      if (!insertionOrderRef.current.includes(n.id)) {
        insertionOrderRef.current.push(n.id);
      }
    }
    const ordered = [...nodes].sort((a, b) => {
      const ix1 = insertionOrderRef.current.indexOf(a.id);
      const ix2 = insertionOrderRef.current.indexOf(b.id);
      return ix1 - ix2;
    });

    const newRfNodes = computeLayout(ordered);

    setRfNodes((prev) => {
      const prevMap = new Map(prev.map((n) => [n.id, n]));
      return newRfNodes.map((n) => {
        const existing = prevMap.get(n.id);
        if (existing) {
          return {
            ...n,
            data: { ...n.data, ...existing.data, ...n.data },
          };
        }
        return n;
      });
    });
  }, [nodes, setRfNodes]);

  /* ---- update edge state on prop changes ---- */
  useEffect(() => {
    setRfEdges((prev) => {
      const seen = new Set(prev.map((e) => e.id));
      const additions: RFEdge[] = [];
      for (const e of edges) {
        if (seen.has(e.id)) continue;
        seen.add(e.id);
        additions.push({
          id: e.id,
          source: e.source,
          target: e.target,
          animated: e.animated ?? false,
          style: {
            stroke: "rgba(255,255,255,0.35)",
            strokeWidth: 1.4,
          },
          markerEnd: {
            type: "arrowclosed" as any,
            width: 14,
            height: 14,
            color: "rgba(255,255,255,0.55)",
          },
        });
      }
      return additions.length ? [...prev, ...additions] : prev;
    });
  }, [edges, setRfEdges]);

  /* ---- keep live "active" / "success" styling fresh on status change ---- */
  useEffect(() => {
    setRfNodes((prev) =>
      prev.map((n) => {
        const updated = nodes.find((x) => x.id === n.id);
        if (!updated) return n;
        const dataAny = n.data as any;
        if (
          dataAny.status === updated.status &&
          JSON.stringify(dataAny.meta || {}) === JSON.stringify(updated.meta || {})
        ) {
          return n;
        }
        return {
          ...n,
          data: {
            ...dataAny,
            status: updated.status,
            meta: updated.meta,
            label: updated.label ?? dataAny.label,
            agent: updated.agent ?? dataAny.agent,
          },
        };
      })
    );
  }, [nodes, setRfNodes]);

  const onNodeClick = useCallback(() => {}, []);

  const proOptions = useMemo(
    () => ({
      hideAttribution: true,
    }),
    []
  );

  const nodeTypes = useMemo(() => ({ agent: AgentNode }), []);

  return (
    <div
      style={{
        width,
        height,
        position: "relative",
        borderRadius: 12,
        overflow: "hidden",
        background:
          "radial-gradient(circle at 30% 20%, rgba(124,58,237,0.10), transparent 60%), hsl(0 0% 4%)",
        border: "1px solid rgba(255,255,255,0.08)",
      }}
    >
      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.45; }
        }
        .reactflow__edge-path { transition: stroke 0.3s ease; }
        .reactflow__node { cursor: default; }
        .reactflow__controls button {
          background: rgba(15,15,15,0.85) !important;
          color: white !important;
          border: 1px solid rgba(255,255,255,0.1) !important;
        }
        .reactflow__controls button:hover {
          background: rgba(40,40,40,0.85) !important;
        }
      `}</style>

      {nodes.length === 0 ? (
        <div
          style={{
            position: "absolute",
            inset: 0,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: "rgba(255,255,255,0.4)",
            fontFamily: "ui-monospace, monospace",
            fontSize: 12,
            textTransform: "uppercase",
            letterSpacing: 2,
          }}
        >
          {isRunning ? "Awaiting first agent action…" : "Execution Graph"}
        </div>
      ) : (
        <ReactFlow
          nodes={rfNodes}
          edges={rfEdges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onNodeClick={onNodeClick}
          nodeTypes={nodeTypes}
          proOptions={proOptions}
          minZoom={0.2}
          maxZoom={1.6}
          panOnDrag
          zoomOnScroll={false}
          zoomOnPinch
        >
          <Background color="rgba(255,255,255,0.06)" gap={18} size={1} />
          <Controls showInteractive={false} />
          <AutoFit nodeCount={rfNodes.length} />
        </ReactFlow>
      )}
    </div>
  );
};
