"use client";

import { useApi } from "@/lib/hooks";
import { AttentionAction, getAttention } from "@/lib/api-client";
import { SourceLink } from "@/components/shared/SourceLink";

function ActionList({ items }: { items: AttentionAction[] }) {
  return (
    <div>
      {items.map((a) => (
        <div key={a.id} className="py-3 border-b border-line last:border-b-0">
          <p className="text-sm text-ink leading-relaxed">{a.description}</p>
          <p className="text-xs text-stone mt-1">
            {a.owner ? `Owner: ${a.owner}` : <span className="text-oxblood">No owner named</span>}
            {a.age_days !== null ? ` · last mentioned ${a.age_days} days ago` : ""}
            {a.projects.length > 0 ? ` · ${a.projects.join(", ")}` : ""}
          </p>
          <div className="mt-1"><SourceLink source={a.source} /></div>
        </div>
      ))}
    </div>
  );
}

function Block({ title, hint, count, children }: { title: string; hint: string; count: number; children: React.ReactNode }) {
  return (
    <section className="mb-10">
      <h2 className="font-serif text-lg text-ink">{title} <span className="text-stone-light text-base">{count}</span></h2>
      <p className="text-xs text-stone mb-3">{hint}</p>
      {count === 0 ? <p className="text-sm text-stone-light">Nothing here.</p> : children}
    </section>
  );
}

export default function AttentionPage() {
  const { data, loading, error } = useApi(getAttention);
  return (
    <div className="px-10 py-8 max-w-4xl">
      <h1 className="font-serif text-2xl text-ink">Needs attention</h1>
      <p className="text-sm text-stone mt-1 mb-8 max-w-prose">
        Gaps in the record that a successor is most likely to trip over. These are signals from the emails, so check
        the source before acting.
      </p>
      {loading && <p className="text-sm text-stone">Reading the record…</p>}
      {error && <p className="text-sm text-oxblood">{error}</p>}
      {data && (
        <>
          <Block title="No named owner" count={data.counts.unowned_actions}
                 hint="Open items nobody was assigned. These tend to fall through when someone leaves.">
            <ActionList items={data.unowned_actions} />
          </Block>
          <Block title="Open and getting old" count={data.counts.stale_actions}
                 hint={`Still open and not mentioned for ${data.thresholds.stale_days}+ days.`}>
            <ActionList items={data.stale_actions} />
          </Block>
          <Block title="Knowledge held by very few people" count={data.counts.concentrated_projects}
                 hint="Projects where the record shows only the predecessor, or only one other person.">
            {data.concentrated_projects.map((p) => (
              <div key={p.id} className="py-3 border-b border-line last:border-b-0 text-sm">
                <span className="text-ink">{p.name}</span>
                <span className="text-stone"> · {p.reason === "only_predecessor"
                  ? "only the predecessor appears with it"
                  : `only ${p.person} appears with it besides the predecessor`}</span>
              </div>
            ))}
          </Block>
          <Block title="Gone quiet, still open" count={data.counts.dormant_projects}
                 hint={`Not mentioned for ${data.thresholds.dormant_days}+ days but with unfinished action items.`}>
            {data.dormant_projects.map((p) => (
              <div key={p.id} className="py-3 border-b border-line last:border-b-0 text-sm">
                <span className="text-ink">{p.name}</span>
                <span className="text-stone"> · quiet since {p.last_seen}, {p.open_actions} open item{p.open_actions === 1 ? "" : "s"}</span>
              </div>
            ))}
          </Block>
        </>
      )}
    </div>
  );
}
