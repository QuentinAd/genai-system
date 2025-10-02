import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import App from "./App.tsx";
import { VibeKanbanWebCompanion } from "vibe-kanban-web-companion";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <VibeKanbanWebCompanion />
    <App />
  </StrictMode>,
);
