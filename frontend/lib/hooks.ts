"use client";

import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@/lib/auth";
import {
  getDashboardSummary,
  DashboardSummary,
  getChatHistory,
  ApiError,
} from "@/lib/api-client";
import type { ChatTurn } from "@/components/chat/ChatMessage";

type State = {
  data: DashboardSummary | null;
  loading: boolean;
  error: string | null;
};

export function useDashboardSummary() {
  const { token } = useAuth();
  const [state, setState] = useState<State>({ data: null, loading: true, error: null });

  const fetchSummary = useCallback(async () => {
    if (!token) return;
    setState((prev) => ({ ...prev, loading: true, error: null }));
    try {
      const data = await getDashboardSummary(token);
      setState({ data, loading: false, error: null });
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Couldn't load the dashboard. Check the backend is running.";
      setState({ data: null, loading: false, error: message });
    }
  }, [token]);

  useEffect(() => {
    fetchSummary();
  }, [fetchSummary]);

  return { ...state, refetch: fetchSummary };
}

type ChatHistoryState = {
  turns: ChatTurn[];
  loading: boolean;
  error: string | null;
};

/**
 * Loads the user's saved conversation from the backend on mount, so switching tabs
 * or reloading the page doesn't lose the chat — it's backed by ChatMessage rows in
 * SQLite (see backend/app/db/models.py), not frontend-only state.
 */
export function useChatHistory() {
  const { token } = useAuth();
  const [state, setState] = useState<ChatHistoryState>({ turns: [], loading: true, error: null });

  useEffect(() => {
    if (!token) return;
    let cancelled = false;

    getChatHistory(token)
      .then((res) => {
        if (!cancelled) setState({ turns: res.turns, loading: false, error: null });
      })
      .catch((err) => {
        if (cancelled) return;
        const message = err instanceof ApiError ? err.message : "Couldn't load past conversation.";
        setState({ turns: [], loading: false, error: message });
      });

    return () => {
      cancelled = true;
    };
  }, [token]);

  return state;
}
