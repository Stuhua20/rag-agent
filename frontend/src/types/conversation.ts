export type DocumentScope = {
  mode: "all" | "selected";
  document_ids: string[];
};

export type Conversation = {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  last_message_preview?: string;
  document_scope?: DocumentScope;
  scope_revision?: number;
  invalid_document_ids?: string[];
};

