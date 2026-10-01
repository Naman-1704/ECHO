const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export type PersonEntry = {
  name: string;
  context_samples: string[];
  mention_count: number;
};

export type ProjectEntry = {
  name: string;
  context_samples: string[];
  mention_count: number;
};

export type Decision = {
  decision: string;
  reasoning: string | null;
  date: string | null;
  chunk_id: string;
  raw_item_id: string;
};

export type ActionItem = {
  description: string;
  owner: string | null;
  status: string;
  chunk_id: string;
  raw_item_id: string;
};

export type DashboardSummary = {
  stats: {
    total_emails_ingested: number;
    total_chunks_processed: number;
    unique_people: number;
    unique_projects: number;
  };
  people: PersonEntry[];
  projects: ProjectEntry[];
  decisions: Decision[];
  pending_actions: ActionItem[];
};

export type ChatSource = {
  index: number;
  raw_item_id: string;
  text_preview: string;
};

export type ChatResponse = {
  answer: string;
  sources: ChatSource[];
};

export type ChatHistoryResponse = {
  turns: { role: "user" | "assistant"; content: string; sources: ChatSource[] }[];
};

export type SyncStats = {
  pulled: number;
  excluded: number;
  chunks_created: number;
  next_page_token: string | null;
};

class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, token: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
      ...(options.headers || {}),
    },
  });

  if (!res.ok) {
    const body = await res.text();
    throw new ApiError(res.status, body || `Request failed with status ${res.status}`);
  }

  return res.json() as Promise<T>;
}

export function getLoginUrl(): string {
  return `${API_BASE}/auth/login`;
}

export async function triggerSync(token: string, maxResults = 10): Promise<SyncStats> {
  return request<SyncStats>(`/ingestion/sync?max_results=${maxResults}`, token, { method: "POST" });
}

export async function getDashboardSummary(token: string): Promise<DashboardSummary> {
  return request<DashboardSummary>("/dashboard/summary", token);
}

export async function askQuestion(token: string, question: string): Promise<ChatResponse> {
  return request<ChatResponse>("/chat/ask", token, {
    method: "POST",
    body: JSON.stringify({ question }),
  });
}

export async function getChatHistory(token: string): Promise<ChatHistoryResponse> {
  return request<ChatHistoryResponse>("/chat/history", token);
}

export async function clearChatHistory(token: string): Promise<{ cleared: boolean }> {
  return request<{ cleared: boolean }>("/chat/history", token, { method: "DELETE" });
}

export { ApiError };
