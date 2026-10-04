import { useQuery } from "@tanstack/react-query";
import { Route, Routes } from "react-router-dom";

import { getHealth } from "../api/client";

function HomePage() {
  const health = useQuery({ queryKey: ["health"], queryFn: getHealth, retry: false });

  return (
    <main className="shell">
      <section className="hero">
        <p className="eyebrow">Shopping Assistant</p>
        <h1>Research products, understand tradeoffs, and build a shortlist.</h1>
        <p>
          Phase 0 scaffold: product workflows are intentionally not implemented yet.
        </p>
        <p role="status">
          {health.isPending
            ? "Checking API connection…"
            : health.isError
              ? "API unavailable. Start the backend and retry."
              : `API status: ${health.data.status}`}
        </p>
        {health.isError && (
          <button type="button" onClick={() => void health.refetch()}>
            Retry connection
          </button>
        )}
      </section>
    </main>
  );
}

export function App() {
  return (
    <Routes>
      <Route path="*" element={<HomePage />} />
    </Routes>
  );
}
