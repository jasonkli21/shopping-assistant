import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { researchApi } from "../../api/client";

export function EvidenceCitation({ projectId, claimId }: { projectId: string; claimId: string }) {
  const [open, setOpen] = useState(false);
  const claim = useQuery({
    queryKey: ["claim-detail", projectId, claimId],
    queryFn: ({ signal }) => researchApi.claim(projectId, claimId, signal),
    enabled: open,
    retry: false,
  });

  return (
    <details className="assistant-evidence-citation" onToggle={(event) => setOpen(event.currentTarget.open)}>
      <summary>Inspect evidence {claimId.slice(0, 8)}</summary>
      {claim.isPending && <p role="status">Loading cited evidence…</p>}
      {claim.isError && <p className="field-error" role="alert">This citation is not available in this project.</p>}
      {claim.data && (
        <div>
          <p><strong>{claim.data.assertion_text}</strong></p>
          <p>{claim.data.evidence_category.replaceAll("_", " ")} · {claim.data.freshness} · {claim.data.source_title ?? "Source title unknown"}</p>
          <p>{claim.data.evidence_excerpt}</p>
          <details><summary>Recorded qualifiers</summary><pre>{JSON.stringify(claim.data.qualifiers, null, 2)}</pre></details>
          <a href={claim.data.source_url} target="_blank" rel="noopener noreferrer">Open source<span className="sr-only"> (opens in a new tab)</span></a>
        </div>
      )}
    </details>
  );
}
