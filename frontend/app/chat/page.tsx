"use client";

import { useEffect, useRef, useState } from "react";
import { AppShell } from "@/components/shared/AppShell";
import { ChatMessage, ChatTurn } from "@/components/chat/ChatMessage";
import { useAuth } from "@/lib/auth";
import { useChatHistory } from "@/lib/hooks";
import { askQuestion, clearChatHistory, ApiError } from "@/lib/api-client";

const SUGGESTED_QUESTIONS = [
  "What projects am I taking over?",
  "Who should I talk to first?",
  "What decisions were made recently and why?",
  "What's still pending or unresolved?",
];

function ChatContent() {
  const { token } = useAuth();
  const history = useChatHistory();

  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [input, setInput] = useState("");
  const [asking, setAsking] = useState(false);
  const [clearing, setClearing] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Seed with whatever Echo remembers from past sessions, once it's loaded.
  useEffect(() => {
    if (!history.loading) setTurns(history.turns);
  }, [history.loading, history.turns]);

  const ask = async (question: string) => {
    if (!token || !question.trim() || asking) return;

    setTurns((prev) => [...prev, { role: "user", content: question }]);
    setInput("");
    setAsking(true);

    try {
      const result = await askQuestion(token, question);
      setTurns((prev) => [...prev, { role: "assistant", content: result.answer, sources: result.sources }]);
    } catch (err) {
      const message =
        err instanceof ApiError ? err.message : "Couldn't reach the backend — is it running?";
      setTurns((prev) => [...prev, { role: "assistant", content: message, sources: [] }]);
    } finally {
      setAsking(false);
      setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: "smooth" }), 50);
    }
  };

  const handleClear = async () => {
    if (!token) return;
    setClearing(true);
    try {
      await clearChatHistory(token);
      setTurns([]);
    } finally {
      setClearing(false);
    }
  };

  const showSuggestions = !history.loading && turns.length === 0;

  return (
    <div className="flex flex-col h-screen">
      <div className="px-10 py-6 border-b border-line flex items-start justify-between">
        <div>
          <h1 className="font-serif text-2xl text-ink">Ask Echo</h1>
          <p className="text-sm text-stone mt-1">
            Answers are grounded only in what's been ingested — every claim links back to its source.
          </p>
        </div>
        {turns.length > 0 && (
          <button
            onClick={handleClear}
            disabled={clearing}
            className="text-xs text-stone hover:text-oxblood transition-colors shrink-0 mt-1"
          >
            {clearing ? "Clearing…" : "Clear conversation"}
          </button>
        )}
      </div>

      <div className="flex-1 overflow-y-auto px-10 py-8">
        {history.loading && <p className="text-sm text-stone">Loading past conversation…</p>}

        {history.error && !history.loading && (
          <p className="text-sm text-oxblood mb-6">{history.error}</p>
        )}

        {showSuggestions && (
          <div className="max-w-2xl">
            <p className="text-sm text-stone mb-4">Try one of these, or ask your own question below.</p>
            <div className="flex flex-col gap-2 items-start">
              {SUGGESTED_QUESTIONS.map((q) => (
                <button
                  key={q}
                  onClick={() => ask(q)}
                  className="text-sm text-ink text-left px-3 py-2 border border-line rounded-sm hover:border-oxblood hover:text-oxblood transition-colors"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        {!history.loading && turns.length > 0 && (
          <div className="max-w-2xl mx-auto flex flex-col gap-4">
            {turns.map((turn, i) => (
              <ChatMessage key={i} turn={turn} />
            ))}
            {asking && <p className="text-sm text-stone pl-9">Echo is thinking…</p>}
            <div ref={bottomRef} />
          </div>
        )}
      </div>

      <div className="px-10 py-6 border-t border-line">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            ask(input);
          }}
          className="max-w-2xl mx-auto flex gap-3"
        >
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about a project, a person, or a decision…"
            className="flex-1 px-4 py-3 text-sm border border-line rounded-sm bg-surface text-ink placeholder:text-stone-light focus:border-ink outline-none"
          />
          <button
            type="submit"
            disabled={asking || !input.trim()}
            className="px-5 py-3 text-sm bg-ink text-paper rounded-sm hover:bg-ink/90 disabled:opacity-50 transition-colors"
          >
            Ask
          </button>
        </form>
      </div>
    </div>
  );
}

export default function ChatPage() {
  return (
    <AppShell>
      <ChatContent />
    </AppShell>
  );
}
