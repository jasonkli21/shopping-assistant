import { Navigate, Route, Routes } from "react-router-dom";

import { ProjectHome } from "../features/projects/ProjectHome";
import { ProjectOverview } from "../features/projects/ProjectOverview";
import { DiscoverPage } from "../features/discovery/DiscoverPage";
import { ProductDetailPage } from "../features/products/ProductDetailPage";

export function App() {
  return (
    <Routes>
      <Route path="/" element={<ProjectHome />} />
      <Route path="/projects/:projectId/discover" element={<DiscoverPage />} />
      <Route path="/products/:productId" element={<ProductDetailPage />} />
      <Route path="/projects/:projectId" element={<ProjectOverview />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
