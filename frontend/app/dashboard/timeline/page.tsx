"use client";

import { useMemo, useState } from "react";
import { useApi } from "@/lib/hooks";
import { getTimeline, TimelineEvent } from "@/lib/api-client";
import { SourceLink } from "@/components/shared/SourceLink";
import { EmptyState } from "@/components/shared/EmptyState";

type Filter = "all" | "decision" | "action";

export default function TimelinePage() {
  const { data, loading, error } = useApi(getTimeline);
  const [filter, setFilter] = useState<Filter>("all");

  const groups = useMemo(() => {
    const events = (data?.events ?? []).filter((e) => filter === "all" || e.type === filter);
    const by = new Map<string, TimelineEvent[]>();
    for (const e of events) {
      const month = (e.date ?? "Undated").slice(0, 7) || "Undated";
      by.set(month, [...(by.get(month) ?? []), e]);
    }
    return [...by.entries()];
  }, [data, filter]);

  return (
    <div className="px-10 py-8 max-w-3xl">
      <h1 className="font-serif text-2xl text-ink">Timeline</h1>
      <p className="text-sm text-stone mt-1 mb-6">Decisions and action items in the order they first appear, newest first.</p>
      <div className="flex gap-2 mb-8">
        {(["all", "decision", "action"] as Filter[]).map((f) => (
          <button key={f} onClick={() => setFilter(f)} aria-pressed={filter === f}
                  className={`px-3 py-1 text-xs border rounded-sm transition-colors ${
                    filter === f ? "bg-ink text-paper border-ink" : "border-line text-stone hover:border-ink"}`}>
            {f === "all" ? "Everything" : f === "decision" ? "Decisions" : "Action items"}
          </button>
        ))}
      </div>
      {loading && <p className="text-sm text-stone">Loading…</p>}
      {error && <p className="text-sm text-oxblood">{error}</p>}
      {data && groups.length === 0 && <EmptyState title="Nothing on the timeline" description="Decisions and action items show up here once the inbox has been synced." />}
      {groups.map(([month, events]) => (
        <section key={month} className="mb-8">
          <h2 className="text-xs uppercase tracking-wide text-stone mb-3">{month}</h2>
          <div className="border-l border-line pl-6 flex flex-col gap-5">
            {events.map((e) => (
              <article key={e.id} className="relative">
                <span className={`absolute -left-[29px] top-1.5 w-2.5 h-2.5 rounded-full ${
                  e.type === "decision" ? "bg-verified" : e.open ? "bg-oxblood" : "bg-stone-light"}`} aria-hidden="true" />
                <p className="text-xs text-stone-light">
                  {e.date} · {e.type === "decision" ? "Decision" : e.open ? "Open action" : "Action (done)"}
                  {e.projects.length > 0 ? ` · ${e.projects.join(", ")}` : ""}
                </p>
                <p className="text-sm text-ink leading-relaxed mt-0.5">{e.text}</p>
                {e.reasoning && <p className="text-sm text-stone leading-relaxed">Reason: {e.reasoning}</p>}
                {e.type === "action" && <p className="text-xs text-stone">{e.owner ? `Owner: ${e.owner}` : "No owner named"}</p>}
                <div className="mt-0.5"><SourceLink source={e.source} /></div>
              </article>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
