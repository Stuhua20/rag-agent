export type DocumentItem = {
  id: string;
  file_name: string;
  original_name: string;
  file_type: string;
  doc_type: string;
  department: string;
  permission_level: number;
  status: string;
  sheet_count: number;
  chunk_count: number;
  row_count: number;
  column_count: number;
  error_message?: string | null;
  created_at: string;
  updated_at: string;
};

export type SheetItem = {
  id: string;
  document_id: string;
  sheet_name: string;
  sheet_index: number;
  header_row: number;
  headers: string[];
  row_count: number;
  column_count: number;
};

export type ChunkItem = {
  id: string;
  document_id: string;
  sheet_id: string;
  chunk_index: number;
  sheet_name: string;
  row_start: number;
  row_end: number;
  columns: string[];
  title: string;
  content: string;
  token_count: number;
};

export type ChunkPage = {
  items: ChunkItem[];
  total: number;
  page: number;
  page_size: number;
};

