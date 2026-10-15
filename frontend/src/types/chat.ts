import type { DocumentScope } from "./conversation";

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: SourceItem[];
  quality?: Record<string, unknown>;
  created_at?: string;
  document_scope?: DocumentScope;
  scope_revision?: number;
};

export type SourceItem = {
  chunk_id: string;
  document_id?: string;
  sheet_id?: string;
  file_name: string;
  sheet_name: string;
  row_start: number;
  row_end: number;
  score: number;
  score_type?: "similarity" | "exact_match";
  content: string;
};

export type ChatRequest = {
  conversation_id?: string | null;
  question: string;
  top_k?: number;
  filters?: Record<string, string | number>;
  expected_scope_revision?: number;
};
