import { API_BASE_URL, request } from "./client";
import type { ChunkPage, DocumentItem, SheetItem } from "../types/document";

export type UploadPayload = {
  file: File;
  fileName: string;
  sourceRelativePath?: string;
};

export type UploadResult = {
  document_id: string;
  status: string;
  sheet_count: number;
  chunk_count: number;
};

export class UploadError extends Error {
  constructor(message: string, public readonly resultUncertain = false) {
    super(message);
    this.name = "UploadError";
  }
}

export function uploadDocument(
  payload: UploadPayload,
  onProgress: (percent: number) => void,
  onTransferred: () => void,
): Promise<UploadResult> {
  const formData = new FormData();
  formData.append("file", payload.file);
  formData.append("file_name", payload.fileName);
  if (payload.sourceRelativePath) formData.append("source_relative_path", payload.sourceRelativePath);

  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress(Math.min(100, Math.floor(event.loaded / event.total * 100)));
    };
    xhr.upload.onload = onTransferred;
    xhr.onerror = () => reject(new UploadError("连接中断，入库结果尚未确认，请先核对文件库。", true));
    xhr.onabort = () => reject(new UploadError("请求已中断，请先核对文件库中的入库结果。", true));
    xhr.onload = () => {
      let body: Partial<UploadResult> & { detail?: unknown };
      try {
        body = JSON.parse(xhr.responseText);
        if (!body || typeof body !== "object") throw new Error();
      } catch {
        reject(new UploadError("无法读取上传结果，请先核对文件库。", true));
        return;
      }
      if (xhr.status < 200 || xhr.status >= 300) {
        reject(new UploadError(
          typeof body.detail === "string" ? body.detail : `上传请求失败（HTTP ${xhr.status}）`,
          xhr.status >= 502,
        ));
      } else if (body.status !== "indexed" || typeof body.document_id !== "string"
        || typeof body.sheet_count !== "number" || typeof body.chunk_count !== "number") {
        reject(new UploadError("尚未确认文件完成入库，请先核对文件库。", true));
      } else {
        resolve(body as UploadResult);
      }
    };
    xhr.open("POST", `${API_BASE_URL}/api/documents/upload`);
    xhr.send(formData);
  });
}

export function fetchDocuments(signal?: AbortSignal) {
  return request<DocumentItem[]>("/api/documents", { signal });
}

export function fetchDocument(documentId: string, signal?: AbortSignal) {
  return request<DocumentItem>(`/api/documents/${documentId}`, { signal });
}

export function fetchSheets(documentId: string, signal?: AbortSignal) {
  return request<SheetItem[]>(`/api/documents/${documentId}/sheets`, { signal });
}

export function fetchChunks(documentId: string, page = 1, pageSize = 50, signal?: AbortSignal) {
  return request<ChunkPage>(`/api/documents/${documentId}/chunks?page=${page}&page_size=${pageSize}`, { signal });
}

export function deleteDocument(documentId: string) {
  return request<{ deleted: boolean }>(`/api/documents/${documentId}`, { method: "DELETE" });
}
