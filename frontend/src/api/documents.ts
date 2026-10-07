import { request } from "./client";
import type { ChunkPage, DocumentItem, SheetItem } from "../types/document";

export type UploadPayload = {
  file: File;
  fileName: string;
  permissionLevel: number;
};

export async function uploadDocument(payload: UploadPayload) {
  const formData = new FormData();
  formData.append("file", payload.file);
  formData.append("file_name", payload.fileName);
  formData.append("permission_level", String(payload.permissionLevel));
  return request<{ document_id: string; status: string; sheet_count: number; chunk_count: number }>(
    "/api/documents/upload",
    { method: "POST", body: formData },
  );
}

export function fetchDocuments() {
  return request<DocumentItem[]>("/api/documents");
}

export function fetchSheets(documentId: string) {
  return request<SheetItem[]>(`/api/documents/${documentId}/sheets`);
}

export function fetchChunks(documentId: string) {
  return request<ChunkPage>(`/api/documents/${documentId}/chunks?page=1&page_size=50`);
}

export function deleteDocument(documentId: string) {
  return request<{ deleted: boolean }>(`/api/documents/${documentId}`, { method: "DELETE" });
}
