import type { PersonEntry } from "@/lib/api-client";

export function PersonRow({ person }: { person: PersonEntry }) {
  return (
    <div className="py-4 border-b border-line last:border-b-0">
      <div className="flex items-baseline justify-between gap-4">
        <p className="font-serif text-base text-ink">{person.name}</p>
        <p className="text-xs text-stone shrink-0">
          mentioned in {person.mention_count} {person.mention_count === 1 ? "thread" : "threads"}
        </p>
      </div>
      {person.context_samples.length > 0 && (
        <ul className="mt-2 space-y-1">
          {person.context_samples.map((sample, i) => (
            <li key={i} className="text-sm text-stone leading-relaxed">
              — {sample}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
