import type { UploadResult } from "../../api/documents";

export type UploadStatus = "pending" | "uploading" | "processing" | "success" | "failed" | "uncertain" | "skipped";

export type UploadItem = {
  id: string;
  file: File;
  relativePath: string;
  displayName: string;
  status: UploadStatus;
  progress: number;
  message?: string;
  result?: UploadResult;
};

export const SUPPORTED_FILES = ".xlsx,.csv,.pdf,.docx";
const MAX_FILE_SIZE = 30 * 1024 * 1024;

export function createUploadItem(file: File): UploadItem {
  const relativePath = file.webkitRelativePath || file.name;
  let message: string | undefined;
  if (relativePath.split("/").some((part) => part === "__MACOSX")
    || file.name === ".DS_Store" || file.name.toLowerCase() === "thumbs.db"
    || file.name.startsWith("~$") || file.name.startsWith("._")) {
    message = "已跳过系统或临时文件";
  } else if (!/\.(xlsx|csv|pdf|docx)$/i.test(file.name)) {
    message = "不支持此格式，仅支持 XLSX / CSV / PDF / DOCX";
  } else if (file.size > MAX_FILE_SIZE) {
    message = "超过单文件 30 MB 限制";
  } else if (file.size === 0) {
    message = "文件为空";
  }
  return {
    id: JSON.stringify([relativePath, file.size, file.lastModified]),
    file,
    relativePath,
    displayName: file.name,
    status: message ? "skipped" : "pending",
    progress: 0,
    message,
  };
}

export function formatFileSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
}
