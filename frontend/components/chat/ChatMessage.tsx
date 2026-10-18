"use client";

import { useState } from "react";
import type { ChatRoute, ChatSource } from "@/lib/api-client";

export type ChatTurn = {
  role: "user" | "assistant";
  content: string;
  sources?: ChatSource[];
  route?: ChatRoute | null;
};

function SourceList({ sources }: { sources: ChatSource[] }) {
  const [openIndex, setOpenIndex] = useState<number | null>(null);

  if (sources.length === 0) return null;

  return (
    <div className="mt-3 pt-3 border-t border-line">
      <p className="text-xs text-stone mb-2">Sources</p>
      <div className="flex flex-wrap gap-1.5">
        {sources.map((s) => (
          <button
            key={s.index}
            className="source-mark"
            onClick={() => setOpenIndex(openIndex === s.index ? null : s.index)}
            aria-expanded={openIndex === s.index}
          >
            {s.index}
          </button>
        ))}
      </div>
      {openIndex !== null && (() => {
        const src = sources.find((x) => x.index === openIndex);
        if (!src) return null;
        return (
          <div className="mt-2 bg-paper border border-line rounded-sm px-3 py-2">
            <div className="flex items-baseline justify-between gap-3 mb-1">
              <p className="text-xs text-ink font-medium truncate">
                {src.subject || "Source"}
                {src.date ? <span className="text-stone-light font-normal"> · {src.date}</span> : null}
              </p>
              {src.url && (
                <a
                  href={src.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs text-oxblood hover:underline shrink-0"
                >
                  Open {src.source_type === "drive" ? "document" : "email"} ↗
                </a>
              )}
            </div>
            <p className="text-xs text-stone leading-relaxed font-serif italic">"{src.text_preview}…"</p>
          </div>
        );
      })()}
    </div>
  );
}

const ROUTE_LABEL: Record<ChatRoute["mode"], string> = {
  graph: "Answered from the relationship graph",
  hybrid: "Graph + document search",
  vector: "Document search",
};

function RouteBadge({ route }: { route: ChatRoute }) {
  const names = route.entities.map((e) => e.name).slice(0, 3).join(", ");
  return (
    <p className="mt-3 text-[11px] text-stone-light leading-snug">
      <span className="text-verified">●</span> {ROUTE_LABEL[route.mode]}
      {route.graph_facts > 0 ? ` · ${route.graph_facts} linked fact${route.graph_facts === 1 ? "" : "s"}` : ""}
      {names ? ` · about ${names}` : ""}
    </p>
  );
}

function EchoAvatar() {
  return (
    <div
      className="shrink-0 w-7 h-7 rounded-full border border-line bg-surface flex items-center justify-center"
      aria-hidden="true"
    >
      <span className="font-serif text-xs text-oxblood">E</span>
    </div>
  );
}

export function ChatMessage({ turn }: { turn: ChatTurn }) {
  const isUser = turn.role === "user";

  if (isUser) {
    return (
      <div className="flex justify-end">
        <div className="max-w-[65ch] px-4 py-3 rounded-sm bg-ink text-paper">
          <p className="text-sm leading-relaxed whitespace-pre-wrap">{turn.content}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex justify-start gap-2.5">
      <EchoAvatar />
      <div className="max-w-[65ch] px-4 py-3 rounded-sm bg-surface border border-line text-ink">
        <p className="text-sm leading-relaxed whitespace-pre-wrap">{turn.content}</p>
        {turn.sources && <SourceList sources={turn.sources} />}
        {turn.route && <RouteBadge route={turn.route} />}
      </div>
    </div>
  );
}
