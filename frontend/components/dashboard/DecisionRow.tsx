import type { Decision } from "@/lib/api-client";

export function DecisionRow({ decision }: { decision: Decision }) {
  return (
    <div className="py-4 border-b border-line last:border-b-0">
      <div className="flex items-start gap-3">
        <span className="mt-1 shrink-0 w-2 h-2 rounded-full bg-verified" aria-hidden="true" />
        <div>
          <p className="text-sm text-ink leading-relaxed">{decision.decision}</p>
          {decision.reasoning && (
            <p className="text-sm text-stone mt-1 leading-relaxed">Reasoning: {decision.reasoning}</p>
          )}
          {decision.date && <p className="text-xs text-stone-light mt-1">{decision.date}</p>}
        </div>
      </div>
    </div>
  );
}
