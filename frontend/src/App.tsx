import { useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import Sidebar from "./components/Sidebar";
import { ToastProvider } from "./components/Toast";
import TopBar from "./components/TopBar";
import ChatPage from "./pages/ChatPage";
import DocumentsPage from "./pages/DocumentsPage";
import PromptsPage from "./pages/PromptsPage";
import SettingsPage from "./pages/SettingsPage";
import UploadPage from "./pages/UploadPage";

export default function App() {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  function toggleSidebar() {
    setSidebarCollapsed((prev) => !prev);
  }

  return (
    <ToastProvider>
      <div className={sidebarCollapsed ? "app-shell sidebar-collapsed" : "app-shell"}>
        <Sidebar collapsed={sidebarCollapsed} onToggle={toggleSidebar} />
        <main className="main-shell">
          <TopBar />
          <Routes>
            <Route path="/" element={<ChatPage />} />
            <Route path="/upload" element={<UploadPage />} />
            <Route path="/documents" element={<DocumentsPage />} />
            <Route path="/prompts" element={<PromptsPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </div>
    </ToastProvider>
  );
}
