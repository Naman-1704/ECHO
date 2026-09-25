"use client";

import { FormEvent, Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { apiRequest } from "../../lib/api";
import { clearSessionToken, getSessionToken, saveSessionToken } from "../../lib/session";

type ChatSource = {
  index: number;
  raw_item_id: string;
  text_preview: string;
};

type ChatResponse = {
  answer: string;
  sources: ChatSource[];
};

type SyncResponse = {
  pulled: number;
  excluded: number;
  chunks_created: number;
  next_page_token?: string | null;
};

export default function DashboardPage() {
  return (
    <Suspense fallback={<main className="shell"><div className="card loading-card">Loading dashboard…</div></main>}>
      <DashboardContent />
    </Suspense>
  );
}

function DashboardContent() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const [ready, setReady] = useState(false);
  const [question, setQuestion] = useState("What projects am I taking over?");
  const [chatResult, setChatResult] = useState<ChatResponse | null>(null);
  const [syncSummary, setSyncSummary] = useState<SyncResponse | null>(null);
  const [isSyncing, setIsSyncing] = useState(false);
  const [isLoadingAnswer, setIsLoadingAnswer] = useState(false);
  const [syncError, setSyncError] = useState<string | null>(null);
  const [chatError, setChatError] = useState<string | null>(null);

  useEffect(() => {
    const tokenFromUrl = searchParams.get("token");

    if (tokenFromUrl) {
      saveSessionToken(tokenFromUrl);
      const nextUrl = new URL(window.location.href);
      nextUrl.searchParams.delete("token");
      window.history.replaceState({}, "", `${nextUrl.pathname}${nextUrl.search}`);
    }

    if (!getSessionToken()) {
      router.replace("/");
      return;
    }

    setReady(true);
  }, [router, searchParams]);

  const handleSync = async () => {
    try {
      setSyncError(null);
      setIsSyncing(true);
      const result = await apiRequest<SyncResponse>(`/ingestion/sync?max_results=10`, {
        method: "POST",
      });
      setSyncSummary(result);
    } catch (error) {
      setSyncError(error instanceof Error ? error.message : "Unable to sync your inbox right now.");
    } finally {
      setIsSyncing(false);
    }
  };

  const handleQuestionSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    if (!question.trim()) {
      setChatError("Please enter a question to ask the assistant.");
      return;
    }

    try {
      setChatError(null);
      setIsLoadingAnswer(true);
      const response = await apiRequest<ChatResponse>("/chat/ask", {
        method: "POST",
        body: JSON.stringify({ question: question.trim() }),
      });
      setChatResult(response);
    } catch (error) {
      setChatError(error instanceof Error ? error.message : "The request could not be completed.");
    } finally {
      setIsLoadingAnswer(false);
    }
  };

  const handleLogout = () => {
    clearSessionToken();
    router.replace("/");
  };

  if (!ready) {
    return <main className="shell"><div className="card loading-card">Loading dashboard…</div></main>;
  }

  return (
    <main className="shell dashboard-shell">
      <header className="topbar card">
        <div>
          <div className="eyebrow">ECHO</div>
          <h2>Knowledge dashboard</h2>
        </div>
        <button className="secondary-button" onClick={handleLogout} type="button">
          Log out
        </button>
      </header>

      <section className="grid-two">
        <div className="card panel">
          <div className="section-header">
            <h3>Inbox sync</h3>
            <button className="primary-button" onClick={handleSync} type="button" disabled={isSyncing}>
              {isSyncing ? "Syncing…" : "Sync Gmail"}
            </button>
          </div>

          <p className="muted">
            Pull recent mail, redact sensitive content, and store the extracted context for later questions.
          </p>

          {syncError ? <div className="alert alert-error">{syncError}</div> : null}

          {syncSummary ? (
            <div className="stats-grid">
              <div className="stat-box">
                <span>Pulled</span>
                <strong>{syncSummary.pulled}</strong>
              </div>
              <div className="stat-box">
                <span>Excluded</span>
                <strong>{syncSummary.excluded}</strong>
              </div>
              <div className="stat-box">
                <span>Chunks</span>
                <strong>{syncSummary.chunks_created}</strong>
              </div>
            </div>
          ) : (
            <div className="empty-state">No sync run yet.</div>
          )}
        </div>

        <div className="card panel">
          <div className="section-header">
            <h3>Ask the assistant</h3>
          </div>

          <form onSubmit={handleQuestionSubmit} className="chat-form">
            <textarea
              aria-label="Question"
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              rows={5}
              placeholder="Ask about your team context, projects, and handoff notes…"
            />

            <button className="primary-button" disabled={isLoadingAnswer} type="submit">
              {isLoadingAnswer ? "Thinking…" : "Ask question"}
            </button>
          </form>

          {chatError ? <div className="alert alert-error">{chatError}</div> : null}

          {chatResult ? (
            <div className="answer-panel">
              <h4>Answer</h4>
              <p>{chatResult.answer}</p>

              {chatResult.sources.length > 0 ? (
                <div className="sources-panel">
                  <h5>Sources</h5>
                  <ul>
                    {chatResult.sources.map((source) => (
                      <li key={`${source.raw_item_id}-${source.index}`}>
                        <span>#{source.index}</span>
                        <small>{source.raw_item_id}</small>
                        <p>{source.text_preview}</p>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </div>
          ) : (
            <div className="empty-state">Ask a question to see the grounded answer here.</div>
          )}
        </div>
      </section>
    </main>
  );
}
