import { Navigate, Route, Routes } from "react-router-dom";

import { ProjectHome } from "../features/projects/ProjectHome";
import { ProjectOverview } from "../features/projects/ProjectOverview";
import { DiscoverPage } from "../features/discovery/DiscoverPage";
import { ProductDetailPage } from "../features/products/ProductDetailPage";
import { ShortlistPage } from "../features/decisions/ShortlistPage";
import { ComparisonPage } from "../features/comparisons/ComparisonPage";
import { ResearchPage } from "../features/research/ResearchPage";
import { SavedProductsPage } from "../features/products/SavedProductsPage";
import { PreferenceProfilePage } from "../features/preferences/PreferenceProfilePage";
import { AuthGate } from "../auth/AuthGate";

export function App() {
  return (
    <AuthGate>
      <Routes>
        <Route path="/" element={<ProjectHome />} />
        <Route path="/projects/:projectId/discover" element={<DiscoverPage />} />
        <Route path="/projects/:projectId/compare" element={<ComparisonPage />} />
        <Route path="/projects/:projectId/compare/:comparisonId" element={<ComparisonPage />} />
        <Route path="/projects/:projectId/shortlist" element={<ShortlistPage />} />
        <Route path="/projects/:projectId/research" element={<ResearchPage />} />
        <Route path="/products/:productId" element={<ProductDetailPage />} />
        <Route path="/saved-products" element={<SavedProductsPage />} />
        <Route path="/profile" element={<PreferenceProfilePage />} />
        <Route path="/projects/:projectId" element={<ProjectOverview />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AuthGate>
  );
}
