export type AppSettings = {
  embedding: {
    provider: string;
    base_url: string;
    model: string;
    mock: boolean;
    normalize: boolean;
  };
  llm: {
    provider: string;
    base_url: string;
    model: string;
    mock: boolean;
  };
  retrieval: {
    top_k: number;
    chunk_size: number;
    overlap: number;
    score_threshold: number;
    search_mode: "hybrid" | "vector" | "keyword";
    max_chunks_per_doc: number;
    full_scan_max_chunks: number;
  };
  conversation: {
    context_window: number;
  };
  secrets?: {
    embedding_api_key_configured: boolean;
    llm_api_key_configured: boolean;
  };
};
