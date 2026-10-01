"use client";

import { useState } from "react";
import { useAuth } from "@/lib/auth";
import { useDashboardSummary } from "@/lib/hooks";
import { triggerSync, ApiError } from "@/lib/api-client";
import { StatBlock } from "@/components/dashboard/StatBlock";
import { DecisionRow } from "@/components/dashboard/DecisionRow";
import { ActionRow } from "@/components/dashboard/ActionRow";
import { EmptyState } from "@/components/shared/EmptyState";

export default function OverviewPage() {
  const { token } = useAuth();
  const { data, loading, error, refetch } = useDashboardSummary();
  const [syncing, setSyncing] = useState(false);
  const [syncMessage, setSyncMessage] = useState<string | null>(null);

  const handleSync = async () => {
    if (!token) return;
    setSyncing(true);
    setSyncMessage(null);
    try {
      const stats = await triggerSync(token);
      setSyncMessage(
        `Pulled ${stats.pulled} emails, excluded ${stats.excluded} as personal/sensitive, created ${stats.chunks_created} record entries.`
      );
      await refetch();
    } catch (err) {
      setSyncMessage(err instanceof ApiError ? err.message : "Sync failed — check the backend is running.");
    } finally {
      setSyncing(false);
    }
  };

  return (
    <div className="px-10 py-8 max-w-4xl">
      <div className="flex items-start justify-between mb-8">
        <div>
          <h1 className="font-serif text-2xl text-ink">Overview</h1>
          <p className="text-sm text-stone mt-1">What's been pulled in and understood so far.</p>
        </div>
        <button
          onClick={handleSync}
          disabled={syncing}
          className="px-4 py-2 text-sm bg-ink text-paper rounded-sm hover:bg-ink/90 disabled:opacity-50 transition-colors shrink-0"
        >
          {syncing ? "Syncing…" : "Sync inbox"}
        </button>
      </div>

      {syncMessage && (
        <p className="text-sm text-stone mb-6 px-4 py-3 bg-surface border border-line rounded-sm">
          {syncMessage}
        </p>
      )}

      {loading && <p className="text-sm text-stone">Loading record…</p>}

      {error && !loading && (
        <p className="text-sm text-oxblood px-4 py-3 bg-oxblood-light border border-oxblood/20 rounded-sm mb-6">
          {error}
        </p>
      )}

      {!loading && !error && data && data.stats.total_chunks_processed === 0 && (
        <EmptyState
          title="Nothing ingested yet"
          description="Pull in the inbox to start building the record — this reads recent emails, filters out personal content, and extracts who's involved in what."
          action={{ label: syncing ? "Working…" : "Sync inbox", onClick: handleSync, loading: syncing }}
        />
      )}

      {!loading && !error && data && data.stats.total_chunks_processed > 0 && (
        <>
          <div className="grid grid-cols-4 gap-6 mb-10">
            <StatBlock value={data.stats.total_emails_ingested} label="Emails read" />
            <StatBlock value={data.stats.unique_people} label="People identified" />
            <StatBlock value={data.stats.unique_projects} label="Projects found" />
            <StatBlock value={data.pending_actions.length} label="Open action items" />
          </div>

          <div className="grid grid-cols-2 gap-10">
            <section>
              <h2 className="font-serif text-lg text-ink mb-1">Pending</h2>
              <p className="text-xs text-stone mb-3">Things left unresolved, as far as the record shows.</p>
              {data.pending_actions.length === 0 ? (
                <p className="text-sm text-stone-light">Nothing flagged as pending.</p>
              ) : (
                <div>
                  {data.pending_actions.slice(0, 8).map((action, i) => (
                    <ActionRow key={i} action={action} />
                  ))}
                </div>
              )}
            </section>

            <section>
              <h2 className="font-serif text-lg text-ink mb-1">Recent decisions</h2>
              <p className="text-xs text-stone mb-3">Choices that were made, with the reasoning behind them.</p>
              {data.decisions.length === 0 ? (
                <p className="text-sm text-stone-light">No decisions extracted yet.</p>
              ) : (
                <div>
                  {data.decisions.slice(0, 8).map((decision, i) => (
                    <DecisionRow key={i} decision={decision} />
                  ))}
                </div>
              )}
            </section>
          </div>
        </>
      )}
    </div>
  );
}
