/**
 * Small deterministic force-directed layout (no dependencies).
 * Nodes start on a circle (so the same data always gives the same picture), then repulsion,
 * edge springs and a weak pull to the centre are iterated with a cooling schedule.
 */
export type LayoutNode = { id: string; r: number; x: number; y: number };
export type LayoutEdge = { source: string; target: string; weight: number };

export function computeLayout(
  nodes: { id: string; r: number }[],
  edges: LayoutEdge[],
  width: number,
  height: number,
  iterations = 320,
): Record<string, { x: number; y: number }> {
  const n = nodes.length;
  const cx = width / 2;
  const cy = height / 2;
  const pts: LayoutNode[] = nodes.map((nd, i) => {
    const a = (2 * Math.PI * i) / Math.max(n, 1);
    const rad = Math.min(width, height) * 0.35;
    return { id: nd.id, r: nd.r, x: cx + rad * Math.cos(a), y: cy + rad * Math.sin(a) };
  });
  const idx = new Map(pts.map((p, i) => [p.id, i]));
  const links = edges
    .map((e) => ({ a: idx.get(e.source), b: idx.get(e.target), w: e.weight }))
    .filter((l): l is { a: number; b: number; w: number } => l.a !== undefined && l.b !== undefined);

  const k = Math.sqrt((width * height) / Math.max(n, 1)) * 0.75; // ideal edge length
  for (let it = 0; it < iterations; it++) {
    const t = 1 - it / iterations;               // cooling: big moves early, fine tuning late
    const dx = new Array(n).fill(0);
    const dy = new Array(n).fill(0);

    for (let i = 0; i < n; i++) {
      for (let j = i + 1; j < n; j++) {
        let vx = pts[i].x - pts[j].x;
        let vy = pts[i].y - pts[j].y;
        let d2 = vx * vx + vy * vy;
        if (d2 < 0.01) { vx = (i % 2 ? 1 : -1) * 0.1; vy = (j % 2 ? 1 : -1) * 0.1; d2 = 0.02; }
        const d = Math.sqrt(d2);
        const f = (k * k) / d;
        dx[i] += (vx / d) * f; dy[i] += (vy / d) * f;
        dx[j] -= (vx / d) * f; dy[j] -= (vy / d) * f;
      }
    }
    for (const l of links) {
      const vx = pts[l.a].x - pts[l.b].x;
      const vy = pts[l.a].y - pts[l.b].y;
      const d = Math.max(Math.sqrt(vx * vx + vy * vy), 0.01);
      const f = ((d * d) / k) * (1 + Math.log(1 + l.w) * 0.35);
      dx[l.a] -= (vx / d) * f; dy[l.a] -= (vy / d) * f;
      dx[l.b] += (vx / d) * f; dy[l.b] += (vy / d) * f;
    }
    const maxMove = 40 * t + 1;
    for (let i = 0; i < n; i++) {
      dx[i] += (cx - pts[i].x) * 0.05;
      dy[i] += (cy - pts[i].y) * 0.05;
      const m = Math.sqrt(dx[i] * dx[i] + dy[i] * dy[i]) || 1;
      const s = Math.min(m, maxMove) / m;
      const pad = pts[i].r + 8;
      pts[i].x = Math.min(width - pad, Math.max(pad, pts[i].x + dx[i] * s));
      pts[i].y = Math.min(height - pad, Math.max(pad, pts[i].y + dy[i] * s));
    }
  }
  return Object.fromEntries(pts.map((p) => [p.id, { x: p.x, y: p.y }]));
}
