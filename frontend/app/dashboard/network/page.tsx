"use client";

import { useState } from "react";
import { useAuth } from "@/lib/auth";
import { useApi } from "@/lib/hooks";
import { getNetwork, getNodeDetail, NodeType, RelatedNode } from "@/lib/api-client";
import { NetworkGraph, NODE_STYLE } from "@/components/network/NetworkGraph";
import { SourceLink } from "@/components/shared/SourceLink";
import { EmptyState } from "@/components/shared/EmptyState";

const TYPE_OPTIONS: NodeType[] = ["person", "project", "decision", "action"];

function Chip({ node, onPick }: { node: RelatedNode; onPick: (id: string) => void }) {
  return (
    <button onClick={() => onPick(node.id)} className="text-left text-sm text-ink hover:text-oxblood transition-colors">
      {node.name}
      <span className="text-xs text-stone-light"> · {node.weight} thread{node.weight === 1 ? "" : "s"}</span>
    </button>
  );
}

function DetailPanel({ id, onPick, onClose }: { id: string; onPick: (id: string) => void; onClose: () => void }) {
  const { data, loading, error } = useApi((t) => getNodeDetail(t, id), [id]);
  if (loading) return <p className="text-sm text-stone">Loading…</p>;
  if (error || !data) return <p className="text-sm text-oxblood">{error ?? "Not found."}</p>;
  const { node } = data;
  const Section = ({ title, items }: { title: string; items: RelatedNode[] }) =>
    items.length === 0 ? null : (
      <div className="mt-5">
        <p className="text-xs uppercase tracking-wide text-stone mb-2">{title}</p>
        <div className="flex flex-col gap-1.5">
          {items.map((n) => <Chip key={n.id} node={n} onPick={onPick} />)}
        </div>
      </div>
    );
  return (
    <div>
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-wide" style={{ color: NODE_STYLE[node.type].fill }}>
            {NODE_STYLE[node.type].label}{node.is_owner ? " · mailbox owner" : ""}
          </p>
          <h2 className="font-serif text-xl text-ink leading-snug">{node.name}</h2>
        </div>
        <button onClick={onClose} className="text-stone hover:text-ink text-lg leading-none" aria-label="Close">×</button>
      </div>
      <p className="text-xs text-stone mt-1">
        {node.mention_count} mention{node.mention_count === 1 ? "" : "s"}
        {node.first_seen ? ` · ${node.first_seen} → ${node.last_seen}` : ""}
      </p>
      {node.aliases.length > 0 && <p className="text-xs text-stone-light mt-1">Also seen as {node.aliases.slice(0, 4).join(", ")}</p>}
      <Section title="People" items={data.people} />
      <Section title="Projects" items={data.projects} />
      {data.decisions.length > 0 && (
        <div className="mt-5">
          <p className="text-xs uppercase tracking-wide text-stone mb-2">Decisions</p>
          {data.decisions.slice(0, 5).map((d) => (
            <p key={d.id} className="text-sm text-ink leading-snug mb-2">{d.decision ?? d.name}</p>
          ))}
        </div>
      )}
      {data.actions.length > 0 && (
        <div className="mt-5">
          <p className="text-xs uppercase tracking-wide text-stone mb-2">Action items</p>
          {data.actions.slice(0, 5).map((a) => (
            <p key={a.id} className="text-sm text-ink leading-snug mb-2">
              <span className={a.open ? "text-oxblood" : "text-verified"}>{a.open ? "Open" : "Done"}</span> · {a.description ?? a.name}
              <span className="text-xs text-stone-light"> {a.owner ? `— ${a.owner}` : "— no owner named"}</span>
            </p>
          ))}
        </div>
      )}
      {data.evidence.length > 0 && (
        <div className="mt-5">
          <p className="text-xs uppercase tracking-wide text-stone mb-2">Where this comes from</p>
          <div className="flex flex-col gap-1.5">
            {data.evidence.map((e, i) => <SourceLink key={i} source={e} />)}
          </div>
        </div>
      )}
    </div>
  );
}

export default function NetworkPage() {
  const { token } = useAuth();
  const [types, setTypes] = useState<NodeType[]>(["person", "project"]);
  const [minWeight, setMinWeight] = useState(1);
  const [hideOwner, setHideOwner] = useState(true);
  const [selected, setSelected] = useState<string | null>(null);
  const { data, loading, error } = useApi(
    (t) => getNetwork(t, { types, minWeight, hideOwner, limit: 80, focus: selected }),
    [types.join(","), minWeight, hideOwner],
  );

  const toggle = (t: NodeType) =>
    setTypes((cur) => (cur.includes(t) ? (cur.length > 1 ? cur.filter((x) => x !== t) : cur) : [...cur, t]));

  return (
    <div className="px-10 py-8 max-w-6xl">
      <h1 className="font-serif text-2xl text-ink">Network</h1>
      <p className="text-sm text-stone mt-1 mb-6 max-w-prose">
        Who appears with what. A line means two things showed up together in the same message or document, and thicker
        means more of them. It does not prove ownership. Drag to rearrange, click for the evidence.
      </p>

      <div className="flex flex-wrap items-center gap-x-6 gap-y-3 mb-4 text-sm">
        <div className="flex gap-2">
          {TYPE_OPTIONS.map((t) => (
            <button
              key={t}
              onClick={() => toggle(t)}
              aria-pressed={types.includes(t)}
              className={`px-3 py-1 border rounded-sm text-xs transition-colors ${
                types.includes(t) ? "bg-ink text-paper border-ink" : "border-line text-stone hover:border-ink"
              }`}
            >
              <span className="inline-block w-2 h-2 rounded-full mr-1.5" style={{ background: NODE_STYLE[t].fill }} />
              {NODE_STYLE[t].label}s
            </button>
          ))}
        </div>
        <label className="flex items-center gap-2 text-xs text-stone">
          Min. shared threads
          <input type="range" min={1} max={5} value={minWeight} onChange={(e) => setMinWeight(+e.target.value)} />
          <span className="text-ink w-3">{minWeight}</span>
        </label>
        <label className="flex items-center gap-2 text-xs text-stone">
          <input type="checkbox" checked={hideOwner} onChange={(e) => setHideOwner(e.target.checked)} />
          Hide the mailbox owner
        </label>
      </div>

      {error && <p className="text-sm text-oxblood mb-4">{error}</p>}
      {!token || (loading && !data) ? (
        <p className="text-sm text-stone">Drawing the network…</p>
      ) : data && data.nodes.length === 0 ? (
        <EmptyState title="No connections yet" description="Sync the inbox first. The network appears once people and projects have been found together." />
      ) : (
        data && (
          <div className="grid grid-cols-[1fr_300px] gap-6 items-start">
            <div>
              <NetworkGraph view={data} selectedId={selected} onSelect={setSelected} />
              <p className="text-xs text-stone-light mt-2">
                Showing {data.stats.shown_nodes} of {data.stats.total_nodes} items
                {data.stats.hidden_isolated > 0 ? ` (${data.stats.hidden_isolated} have no connections here)` : ""}.
                Dashed lines are people who write to each other; squares are projects.
              </p>
            </div>
            <aside className="bg-surface border border-line rounded-sm p-5 min-h-[200px] sticky top-6 max-h-[calc(100vh-3rem)] overflow-y-auto">
              {selected ? (
                <DetailPanel id={selected} onPick={setSelected} onClose={() => setSelected(null)} />
              ) : (
                <p className="text-sm text-stone">Select a person or project to see who is connected to it, what was decided, and the emails behind it.</p>
              )}
            </aside>
          </div>
        )
      )}
    </div>
  );
}
