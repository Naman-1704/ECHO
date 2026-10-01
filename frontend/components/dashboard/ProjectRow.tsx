import type { ProjectEntry } from "@/lib/api-client";

export function ProjectRow({ project }: { project: ProjectEntry }) {
  return (
    <div className="py-4 border-b border-line last:border-b-0">
      <div className="flex items-baseline justify-between gap-4">
        <p className="font-serif text-base text-ink">{project.name}</p>
        <p className="text-xs text-stone shrink-0">
          referenced {project.mention_count} {project.mention_count === 1 ? "time" : "times"}
        </p>
      </div>
      {project.context_samples.length > 0 && (
        <ul className="mt-2 space-y-1">
          {project.context_samples.map((sample, i) => (
            <li key={i} className="text-sm text-stone leading-relaxed">
              — {sample}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
