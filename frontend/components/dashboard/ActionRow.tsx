import type { ActionItem } from "@/lib/api-client";

export function ActionRow({ action }: { action: ActionItem }) {
  return (
    <div className="py-4 border-b border-line last:border-b-0">
      <div className="flex items-start gap-3">
        <span className="mt-1 shrink-0 w-2 h-2 rounded-full bg-oxblood" aria-hidden="true" />
        <div>
          <p className="text-sm text-ink leading-relaxed">{action.description}</p>
          {action.owner && <p className="text-xs text-stone mt-1">Owner: {action.owner}</p>}
        </div>
      </div>
    </div>
  );
}
