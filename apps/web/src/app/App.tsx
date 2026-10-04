import { Navigate, Route, Routes } from "react-router-dom";

import { ProjectHome } from "../features/projects/ProjectHome";
import { ProjectOverview } from "../features/projects/ProjectOverview";

export function App() {
  return (
    <Routes>
      <Route path="/" element={<ProjectHome />} />
      <Route path="/projects/:projectId" element={<ProjectOverview />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
