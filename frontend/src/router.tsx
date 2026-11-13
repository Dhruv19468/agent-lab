import { createBrowserRouter } from "react-router";

import { AppShell } from "./components/AppShell";
import { AgentDetailPage } from "./pages/AgentDetailPage";
import { AgentsPage } from "./pages/AgentsPage";
import { DashboardPage } from "./pages/DashboardPage";
import { NotFoundPage } from "./pages/NotFoundPage";
import { SkillEditorPage } from "./pages/SkillEditorPage";
import { SkillsPage } from "./pages/SkillsPage";
import { ToolEditorPage } from "./pages/ToolEditorPage";
import { ToolsPage } from "./pages/ToolsPage";

export const router = createBrowserRouter([
  {
    path: "/",
    element: <AppShell />,
    children: [
      { index: true, element: <DashboardPage /> },
      { path: "agents", element: <AgentsPage /> },
      { path: "agents/:agentId", element: <AgentDetailPage /> },
      { path: "skills", element: <SkillsPage /> },
      { path: "skills/new", element: <SkillEditorPage key="new-skill" /> },
      { path: "skills/:skillId", element: <SkillEditorPage /> },
      { path: "tools", element: <ToolsPage /> },
      { path: "tools/new", element: <ToolEditorPage key="new-tool" /> },
      { path: "tools/:toolId", element: <ToolEditorPage /> },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
]);
