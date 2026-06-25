export type AppSettings = {
  embedding: {
    provider: string;
    base_url: string;
    model: string;
    mock: boolean;
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
  };
  secrets?: {
    embedding_api_key_configured: boolean;
    llm_api_key_configured: boolean;
  };
};
