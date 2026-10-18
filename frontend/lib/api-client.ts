const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export type PersonEntry = {
  id?: string;
  name: string;
  aliases?: string[];
  last_seen?: string | null;
  context_samples: string[];
  mention_count: number;
};

export type ProjectEntry = {
  id?: string;
  name: string;
  aliases?: string[];
  last_seen?: string | null;
  context_samples: string[];
  mention_count: number;
};

export type Decision = {
  decision: string;
  reasoning: string | null;
  date: string | null;
  chunk_id: string;
  raw_item_id: string;
  source?: SourceRef | null;
};

export type ActionItem = {
  description: string;
  owner: string | null;
  status: string;
  last_seen?: string | null;
  chunk_id: string;
  raw_item_id: string;
  source?: SourceRef | null;
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
  chunk_id?: string;
  raw_item_id: string;
  source_type?: string;
  subject?: string;
  date?: string | null;
  url?: string | null;
  text_preview: string;
};

export type ChatRoute = {
  mode: "graph" | "hybrid" | "vector";
  entities: { id?: string; name: string; type?: string }[];
  graph_facts: number;
  documents: number;
};

export type ChatResponse = {
  answer: string;
  sources: ChatSource[];
  route?: ChatRoute | null;
};

export type ChatHistoryResponse = {
  turns: { role: "user" | "assistant"; content: string; sources: ChatSource[]; route?: ChatRoute | null }[];
};

export type SyncSource = "gmail" | "drive" | "all";

export type SyncStats = {
  pulled: number;
  excluded: number;
  skipped_existing?: number;
  chunks_created: number;
  by_source?: { gmail: number; drive: number };
  errors?: string[];
  next_page_token: string | null;
  graph?: { nodes: number; edges: number; people: number; projects: number; decisions: number; actions: number };
};

export type SourceRef = {
  subject: string;
  date: string | null;
  url: string | null;
  source: string;
};

export type NodeType = "person" | "project" | "decision" | "action";

export type GraphNodeView = {
  id: string;
  type: NodeType;
  name: string;
  mention_count: number;
  degree: number;
  weighted_degree: number;
  is_owner: boolean;
  last_seen: string | null;
};

export type GraphEdgeView = { source: string; target: string; relation: string; weight: number };

export type GraphView = {
  nodes: GraphNodeView[];
  edges: GraphEdgeView[];
  stats: { total_nodes: number; total_edges: number; shown_nodes: number; shown_edges: number; hidden_isolated: number };
};

export type RelatedNode = {
  id: string;
  type: NodeType;
  name: string;
  relation: string;
  weight: number;
  last_seen: string | null;
  is_owner: boolean;
  decision?: string;
  reasoning?: string | null;
  date?: string | null;
  description?: string;
  owner?: string | null;
  status?: string;
  open?: boolean;
};

export type NodeDetail = {
  node: {
    id: string;
    type: NodeType;
    name: string;
    aliases: string[];
    mention_count: number;
    first_seen: string | null;
    last_seen: string | null;
    is_owner: boolean;
    attrs: Record<string, unknown>;
  };
  people: RelatedNode[];
  projects: RelatedNode[];
  decisions: RelatedNode[];
  actions: RelatedNode[];
  evidence: (SourceRef & { chunk_id?: string; text_preview?: string })[];
};

export type AttentionAction = {
  id: string;
  description: string;
  owner: string | null;
  status: string;
  last_seen: string | null;
  age_days: number | null;
  projects: string[];
  source?: SourceRef | null;
};

export type AttentionReport = {
  thresholds: { stale_days: number; dormant_days: number };
  counts: {
    open_actions: number;
    stale_actions: number;
    unowned_actions: number;
    concentrated_projects: number;
    dormant_projects: number;
  };
  stale_actions: AttentionAction[];
  unowned_actions: AttentionAction[];
  concentrated_projects: {
    id: string;
    name: string;
    reason: "only_predecessor" | "one_person";
    person: string | null;
    mentions: number;
    last_seen: string | null;
  }[];
  dormant_projects: { id: string; name: string; last_seen: string; days_quiet: number; open_actions: number }[];
};

export type KeyPerson = {
  id: string;
  name: string;
  weighted_degree: number;
  mention_count: number;
  last_seen: string | null;
  emails: string[];
  roles: string[];
  projects: { id: string; name: string; weight: number }[];
};

export type KeyPeople = { owner: KeyPerson | null; people: KeyPerson[] };

export type TimelineEvent = {
  id: string;
  type: "decision" | "action";
  date: string | null;
  last_seen: string | null;
  text: string | null;
  reasoning: string | null;
  owner: string | null;
  status: string | null;
  open: boolean | null;
  projects: string[];
  source: SourceRef | null;
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

export async function triggerSync(token: string, source: SyncSource = "gmail", maxResults = 50): Promise<SyncStats> {
  return request<SyncStats>(`/ingestion/sync?source=${source}&max_results=${maxResults}`, token, { method: "POST" });
}

export async function getNetwork(
  token: string,
  opts: { types: NodeType[]; minWeight: number; hideOwner: boolean; limit?: number; focus?: string | null },
): Promise<GraphView> {
  const q = new URLSearchParams({
    types: opts.types.join(","),
    min_weight: String(opts.minWeight),
    hide_owner: String(opts.hideOwner),
    limit: String(opts.limit ?? 80),
  });
  if (opts.focus) q.set("focus", opts.focus);
  return request<GraphView>(`/graph/network?${q.toString()}`, token);
}

export async function getNodeDetail(token: string, id: string): Promise<NodeDetail> {
  return request<NodeDetail>(`/graph/node/${encodeURIComponent(id)}`, token);
}

export async function rebuildGraph(token: string): Promise<Record<string, number>> {
  return request<Record<string, number>>("/graph/rebuild", token, { method: "POST" });
}

export async function getAttention(token: string): Promise<AttentionReport> {
  return request<AttentionReport>("/insights/attention", token);
}

export async function getKeyPeople(token: string, limit = 6): Promise<KeyPeople> {
  return request<KeyPeople>(`/insights/key-people?limit=${limit}`, token);
}

export async function getTimeline(token: string): Promise<{ events: TimelineEvent[] }> {
  return request<{ events: TimelineEvent[] }>("/insights/timeline", token);
}

/** Fetches the report with the auth header, then hands the browser a blob to save. */
export async function downloadHandoverReport(token: string, format: "pdf" | "md"): Promise<void> {
  const res = await fetch(`${API_BASE}/reports/handover?format=${format}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new ApiError(res.status, (await res.text()) || "Couldn't build the report.");
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `echo-handover-report.${format}`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
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
