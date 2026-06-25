export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
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
  content: string;
};

export type ChatRequest = {
  conversation_id?: string | null;
  question: string;
  top_k?: number;
  filters?: Record<string, string | number>;
};

export type ChatResponse = {
  conversation_id: string;
  answer: string;
  sources: SourceItem[];
};
