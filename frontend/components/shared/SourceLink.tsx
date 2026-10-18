import type { SourceRef } from "@/lib/api-client";

/** A quiet link back to the original email or document, or plain text when there is no URL. */
export function SourceLink({ source }: { source?: SourceRef | null }) {
  if (!source) return null;
  const label = `${source.subject}${source.date ? ` · ${source.date}` : ""}`;
  const text = <span className="truncate max-w-[34ch] inline-block align-bottom">{label}</span>;
  return source.url ? (
    <a href={source.url} target="_blank" rel="noopener noreferrer"
       className="text-xs text-oxblood hover:underline inline-flex items-center gap-1">
      {text}<span aria-hidden="true">↗</span>
    </a>
  ) : (
    <span className="text-xs text-stone-light">{text}</span>
  );
}
