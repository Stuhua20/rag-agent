import { Link } from "react-router-dom";
import { useUpload } from "../components/upload/UploadProvider";

export default function UploadPage() {
  const { open, isRunning } = useUpload();

  return (
    <div className="page-panel">
      <h1>上传资料</h1>
      <p>支持多选文件，或选择文件夹导入所有子目录中的 XLSX / CSV / PDF / DOCX 文件。</p>
      <button type="button" onClick={open} aria-haspopup="dialog">
        {isRunning ? "查看上传进度" : "选择文件或文件夹"}
      </button>
      <p className="upload-page-nav"><Link to="/documents">前往文件库查看</Link></p>
    </div>
  );
}
