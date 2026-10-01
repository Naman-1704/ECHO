"use client";

import { useDashboardSummary } from "@/lib/hooks";
import { ProjectRow } from "@/components/dashboard/ProjectRow";
import { EmptyState } from "@/components/shared/EmptyState";

export default function ProjectsPage() {
  const { data, loading, error } = useDashboardSummary();

  return (
    <div className="px-10 py-8 max-w-3xl">
      <h1 className="font-serif text-2xl text-ink mb-1">Projects</h1>
      <p className="text-sm text-stone mb-8">Every project mentioned across the inbox, most-referenced first.</p>

      {loading && <p className="text-sm text-stone">Loading…</p>}
      {error && <p className="text-sm text-oxblood">{error}</p>}

      {!loading && !error && data && data.projects.length === 0 && (
        <EmptyState
          title="No projects found yet"
          description="Sync the inbox from the Overview page to start building this list."
        />
      )}

      {!loading && !error && data && data.projects.length > 0 && (
        <div className="bg-surface border border-line rounded-sm px-6">
          {data.projects.map((project) => (
            <ProjectRow key={project.name} project={project} />
          ))}
        </div>
      )}
    </div>
  );
}
