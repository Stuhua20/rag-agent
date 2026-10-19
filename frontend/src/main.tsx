import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import "./styles/global.css";
import "./styles/layout.css";
import "./styles/upload.css";
import "./styles/document-preview.css";
import "./styles/document-scope.css";
import "./styles/answer.css";
import "./styles/agent-progress.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>,
);

