"use client";

import { useDashboardSummary } from "@/lib/hooks";
import { PersonRow } from "@/components/dashboard/PersonRow";
import { EmptyState } from "@/components/shared/EmptyState";

export default function PeoplePage() {
  const { data, loading, error } = useDashboardSummary();

  return (
    <div className="px-10 py-8 max-w-3xl">
      <h1 className="font-serif text-2xl text-ink mb-1">People</h1>
      <p className="text-sm text-stone mb-8">Everyone who shows up in the record, most-mentioned first.</p>

      {loading && <p className="text-sm text-stone">Loading…</p>}
      {error && <p className="text-sm text-oxblood">{error}</p>}

      {!loading && !error && data && data.people.length === 0 && (
        <EmptyState
          title="No people identified yet"
          description="Sync the inbox from the Overview page to start building this list."
        />
      )}

      {!loading && !error && data && data.people.length > 0 && (
        <div className="bg-surface border border-line rounded-sm px-6">
          {data.people.map((person) => (
            <PersonRow key={person.name} person={person} />
          ))}
        </div>
      )}
    </div>
  );
}
