"use client";

import { useMemo, useRef, useState } from "react";
import type { GraphView, NodeType } from "@/lib/api-client";
import { computeLayout } from "@/lib/forceLayout";

const W = 900;
const H = 600;

export const NODE_STYLE: Record<NodeType, { fill: string; label: string }> = {
  person: { fill: "#1B2430", label: "Person" },
  project: { fill: "#8A2E22", label: "Project" },
  decision: { fill: "#3F6659", label: "Decision" },
  action: { fill: "#A9A39C", label: "Action" },
};

function radius(weighted: number, max: number) {
  return 7 + 15 * Math.sqrt(weighted / Math.max(max, 1));
}

type Props = {
  view: GraphView;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
};

export function NetworkGraph({ view, selectedId, onSelect }: Props) {
  const maxW = Math.max(1, ...view.nodes.map((n) => n.weighted_degree));
  const base = useMemo(
    () =>
      computeLayout(
        view.nodes.map((n) => ({ id: n.id, r: radius(n.weighted_degree, maxW) })),
        view.edges,
        W,
        H,
      ),
    [view, maxW],
  );
  const [moved, setMoved] = useState<Record<string, { x: number; y: number }>>({});
  const [hover, setHover] = useState<string | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const drag = useRef<{ id: string; moved: boolean } | null>(null);

  const pos = (id: string) => moved[id] ?? base[id] ?? { x: W / 2, y: H / 2 };

  const neighbours = useMemo(() => {
    const m = new Map<string, Set<string>>();
    for (const e of view.edges) {
      (m.get(e.source) ?? m.set(e.source, new Set()).get(e.source)!).add(e.target);
      (m.get(e.target) ?? m.set(e.target, new Set()).get(e.target)!).add(e.source);
    }
    return m;
  }, [view.edges]);

  const active = hover ?? selectedId;
  const lit = (id: string) => !active || id === active || neighbours.get(active)?.has(id);

  const toSvg = (ev: React.PointerEvent) => {
    const svg = svgRef.current!;
    const r = svg.getBoundingClientRect();
    return { x: ((ev.clientX - r.left) / r.width) * W, y: ((ev.clientY - r.top) / r.height) * H };
  };

  return (
    <svg
      ref={svgRef}
      viewBox={`0 0 ${W} ${H}`}
      className="w-full h-auto bg-surface border border-line rounded-sm touch-none select-none"
      role="img"
      aria-label="Network of people and projects"
      onPointerMove={(ev) => {
        if (!drag.current) return;
        drag.current.moved = true;
        const p = toSvg(ev);
        setMoved((m) => ({ ...m, [drag.current!.id]: p }));
      }}
      onPointerUp={() => {
        const d = drag.current;
        drag.current = null;
        if (d && !d.moved) onSelect(d.id === selectedId ? null : d.id);
      }}
      onPointerLeave={() => (drag.current = null)}
      onClick={(e) => { if (e.target === svgRef.current) onSelect(null); }}
    >
      <g>
        {view.edges.map((e, i) => {
          const a = pos(e.source), b = pos(e.target);
          const on = !active || e.source === active || e.target === active;
          return (
            <line
              key={i}
              x1={a.x} y1={a.y} x2={b.x} y2={b.y}
              stroke={on && active ? "#8A2E22" : "#6B6560"}
              strokeOpacity={on ? (active ? 0.7 : 0.35) : 0.07}
              strokeWidth={Math.min(1 + Math.log2(1 + e.weight) * 1.2, 6)}
              strokeDasharray={e.relation === "COLLABORATES_WITH" ? "4 3" : undefined}
            />
          );
        })}
      </g>
      <g>
        {view.nodes.map((n) => {
          const p = pos(n.id);
          const r = radius(n.weighted_degree, maxW);
          const style = NODE_STYLE[n.type];
          const isSel = n.id === selectedId;
          const opacity = lit(n.id) ? 1 : 0.18;
          const showLabel = r > 11 || n.id === active || neighbours.get(active ?? "")?.has(n.id) || view.nodes.length <= 30;
          return (
            <g
              key={n.id}
              transform={`translate(${p.x},${p.y})`}
              opacity={opacity}
              style={{ cursor: "pointer" }}
              onPointerDown={(ev) => { (ev.target as Element).setPointerCapture?.(ev.pointerId); drag.current = { id: n.id, moved: false }; }}
              onPointerEnter={() => setHover(n.id)}
              onPointerOut={() => setHover(null)}
            >
              {n.type === "project" ? (
                <rect x={-r} y={-r} width={r * 2} height={r * 2} rx={2} fill={style.fill}
                      stroke={isSel ? "#1B2430" : "#EDEBE4"} strokeWidth={isSel ? 3 : 1.5} />
              ) : (
                <circle r={r} fill={style.fill} stroke={isSel ? "#8A2E22" : "#EDEBE4"} strokeWidth={isSel ? 3 : 1.5} />
              )}
              {n.is_owner && <circle r={r + 4} fill="none" stroke="#3F6659" strokeWidth={1.5} strokeDasharray="2 2" />}
              {showLabel && (
                <text y={r + 13} textAnchor="middle" fontSize={11} fill="#1B2430"
                      stroke="#FFFFFF" strokeWidth={3} paintOrder="stroke" style={{ pointerEvents: "none" }}>
                  {n.name.length > 24 ? n.name.slice(0, 23) + "…" : n.name}
                </text>
              )}
            </g>
          );
        })}
      </g>
    </svg>
  );
}
