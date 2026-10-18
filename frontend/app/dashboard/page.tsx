"use client";

import { useState } from "react";
import { useAuth } from "@/lib/auth";
import { useApi, useDashboardSummary } from "@/lib/hooks";
import { triggerSync, getKeyPeople, downloadHandoverReport, ApiError, SyncSource } from "@/lib/api-client";
import { StatBlock } from "@/components/dashboard/StatBlock";
import { DecisionRow } from "@/components/dashboard/DecisionRow";
import { ActionRow } from "@/components/dashboard/ActionRow";
import { EmptyState } from "@/components/shared/EmptyState";

export default function OverviewPage() {
  const { token } = useAuth();
  const { data, loading, error, refetch } = useDashboardSummary();
  const [syncing, setSyncing] = useState(false);
  const [syncMessage, setSyncMessage] = useState<string | null>(null);
  const [source, setSource] = useState<SyncSource>("gmail");
  const [reporting, setReporting] = useState<"pdf" | "md" | null>(null);
  const people = useApi((t) => getKeyPeople(t, 5));

  const handleReport = async (format: "pdf" | "md") => {
    if (!token) return;
    setReporting(format);
    try {
      await downloadHandoverReport(token, format);
    } catch (err) {
      setSyncMessage(err instanceof ApiError ? err.message : "Couldn't build the report.");
    } finally {
      setReporting(null);
    }
  };

  const handleSync = async () => {
    if (!token) return;
    setSyncing(true);
    setSyncMessage(null);
    try {
      const stats = await triggerSync(token, source);
      const parts = [
        `Pulled ${stats.pulled} item${stats.pulled === 1 ? "" : "s"}`,
        `excluded ${stats.excluded} as personal/sensitive`,
        `created ${stats.chunks_created} record entries`,
      ];
      if (stats.by_source) parts.push(`${stats.by_source.gmail} emails, ${stats.by_source.drive} documents`);
      setSyncMessage(parts.join(", ") + "." + (stats.errors?.length ? ` Problems: ${stats.errors.join("; ")}` : ""));
      await refetch();
      people.refetch();
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
        <div className="flex items-center gap-2 shrink-0">
          <select
            value={source}
            onChange={(e) => setSource(e.target.value as SyncSource)}
            disabled={syncing}
            aria-label="What to sync"
            className="px-2 py-2 text-sm border border-line rounded-sm bg-surface text-ink"
          >
            <option value="gmail">Gmail</option>
            <option value="drive">Drive documents</option>
            <option value="all">Gmail + Drive</option>
          </select>
          <button
            onClick={handleSync}
            disabled={syncing}
            className="px-4 py-2 text-sm bg-ink text-paper rounded-sm hover:bg-ink/90 disabled:opacity-50 transition-colors"
          >
            {syncing ? "Syncing…" : "Sync"}
          </button>
        </div>
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

          {people.data && people.data.people.length > 0 && (
            <section className="mb-10">
              <h2 className="font-serif text-lg text-ink mb-1">Who to talk to first</h2>
              <p className="text-xs text-stone mb-3">The people who appear with the most projects and colleagues.</p>
              <div className="flex flex-wrap gap-3">
                {people.data.people.map((p) => (
                  <div key={p.id} className="bg-surface border border-line rounded-sm px-4 py-3 min-w-[170px]">
                    <p className="text-sm text-ink font-medium">{p.name}</p>
                    <p className="text-xs text-stone mt-0.5">
                      {p.projects.length > 0 ? p.projects.slice(0, 2).map((x) => x.name).join(", ") : "no project link"}
                    </p>
                    {p.emails[0] && <p className="text-xs text-stone-light mt-0.5">{p.emails[0]}</p>}
                  </div>
                ))}
              </div>
            </section>
          )}

          <section className="mb-10 flex items-center justify-between gap-6 bg-surface border border-line rounded-sm px-5 py-4">
            <div>
              <p className="font-serif text-base text-ink">Handover report</p>
              <p className="text-xs text-stone">Everything above in one document, with links back to each email or file.</p>
            </div>
            <div className="flex gap-2 shrink-0">
              <button onClick={() => handleReport("pdf")} disabled={reporting !== null}
                      className="px-3 py-2 text-sm bg-oxblood text-paper rounded-sm hover:bg-oxblood/90 disabled:opacity-50">
                {reporting === "pdf" ? "Building…" : "Download PDF"}
              </button>
              <button onClick={() => handleReport("md")} disabled={reporting !== null}
                      className="px-3 py-2 text-sm border border-line text-ink rounded-sm hover:border-ink disabled:opacity-50">
                {reporting === "md" ? "Building…" : "Markdown"}
              </button>
            </div>
          </section>

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
