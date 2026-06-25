import { FormEvent, useState } from "react";
import { uploadDocument } from "../api/documents";

export default function FileUploader() {
  const [file, setFile] = useState<File | null>(null);
  const [fileName, setFileName] = useState("");
  const [docType, setDocType] = useState("表格文件");
  const [department, setDepartment] = useState("默认部门");
  const [permissionLevel, setPermissionLevel] = useState(1);
  const [status, setStatus] = useState("");
  const [loading, setLoading] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!file) {
      setStatus("请选择 xlsx 或 csv 文件");
      return;
    }
    setLoading(true);
    setStatus("正在上传并解析表格...");
    try {
      const result = await uploadDocument({
        file,
        fileName: fileName || file.name,
        docType,
        department,
        permissionLevel,
      });
      setStatus(`上传成功：${result.document_id}，Sheets ${result.sheet_count}，Chunks ${result.chunk_count}`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "上传失败");
    } finally {
      setLoading(false);
    }
  }

  return (
    <form className="form-panel" onSubmit={onSubmit}>
      <label>
        文件
        <input type="file" accept=".xlsx,.xls,.csv" onChange={(event) => setFile(event.target.files?.[0] ?? null)} />
      </label>
      <label>
        文件名称
        <input value={fileName} onChange={(event) => setFileName(event.target.value)} placeholder="默认使用原文件名" />
      </label>
      <label>
        文档类型
        <input value={docType} onChange={(event) => setDocType(event.target.value)} />
      </label>
      <label>
        所属部门
        <input value={department} onChange={(event) => setDepartment(event.target.value)} />
      </label>
      <label>
        权限等级
        <input
          type="number"
          min={1}
          value={permissionLevel}
          onChange={(event) => setPermissionLevel(Number(event.target.value))}
        />
      </label>
      <button type="submit" disabled={loading}>{loading ? "处理中..." : "上传并解析"}</button>
      {status && <p className="status-text">{status}</p>}
    </form>
  );
}

