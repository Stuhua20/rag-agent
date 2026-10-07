import { useState } from "react";
import { useNavigate } from "react-router-dom";
import FileUploader from "../components/FileUploader";

export default function UploadPage() {
  const navigate = useNavigate();
  const [uploaded, setUploaded] = useState(false);

  return (
    <div className="page-panel">
      <h1>上传 Excel / CSV / PDF / Word</h1>
      <FileUploader
        onUploaded={() => {
          setUploaded(true);
        }}
      />
      {uploaded && (
        <div className="upload-page-nav">
          <button type="button" onClick={() => navigate("/documents")}>
            前往文件库查看
          </button>
        </div>
      )}
    </div>
  );
}
