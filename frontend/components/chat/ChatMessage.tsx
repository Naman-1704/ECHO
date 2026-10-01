"use client";

import { useState } from "react";
import type { ChatSource } from "@/lib/api-client";

export type ChatTurn = {
  role: "user" | "assistant";
  content: string;
  sources?: ChatSource[];
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
      {openIndex !== null && (
        <div className="mt-2 bg-paper border border-line rounded-sm px-3 py-2">
          <p className="text-xs text-stone leading-relaxed font-serif italic">
            "{sources.find((s) => s.index === openIndex)?.text_preview}…"
          </p>
        </div>
      )}
    </div>
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
      </div>
    </div>
  );
}
