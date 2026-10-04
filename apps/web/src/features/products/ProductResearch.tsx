import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { ApiRequestError, projectsApi, researchApi } from "../../api/client";

type EvidenceSelection = { kind: "claim" | "source"; id: string };

function safeUrl(value: string) {
  try {
    const url = new URL(value);
    return ["https:", "http:"].includes(url.protocol) && !url.username && !url.password
      ? url.href : undefined;
  } catch {
    return undefined;
  }
}

function dateLabel(value: string | null) {
  return value ? new Date(value).toLocaleDateString() : "Publication date unknown";
}

function readableError(error: unknown) {
  return error instanceof Error ? error.message : "Research could not load.";
}

export function ProductResearch({ projectId, projectProductId }: {
  projectId: string;
  projectProductId: string;
}) {
  const queryClient = useQueryClient();
  const [selection, setSelection] = useState<EvidenceSelection | null>(null);
  const opener = useRef<HTMLElement | null>(null);
  const closeButton = useRef<HTMLButtonElement | null>(null);
  const project = useQuery({
    queryKey: ["project", projectId],
    queryFn: ({ signal }) => projectsApi.get(projectId, signal),
    retry: false,
  });
  const evidence = useQuery({
    queryKey: ["product-research", projectId, projectProductId],
    queryFn: ({ signal }) => researchApi.productEvidence(projectId, projectProductId, signal),
    retry: false,
    refetchInterval: 4000,
  });
  const runs = useQuery({
    queryKey: ["research-runs", projectId],
    queryFn: ({ signal }) => researchApi.list(projectId, 20, undefined, signal),
    retry: false,
    refetchInterval: 4000,
  });
  const activeRun = runs.data?.items.find((run) =>
    ["queued", "running"].includes(run.status) && run.targets?.some((target) => target.project_product_id === projectProductId)
  );
  const latestRun = runs.data?.items.find((run) =>
    run.type === "product_research" && run.targets?.some((target) => target.project_product_id === projectProductId)
  );
  const runDetail = useQuery({
    queryKey: ["research-run-detail", projectId, activeRun?.id],
    queryFn: ({ signal }) => researchApi.get(projectId, activeRun!.id, signal),
    enabled: Boolean(activeRun),
    retry: false,
    refetchInterval: 4000,
  });
  const create = useMutation({
    mutationFn: async () => {
      const fresh = await projectsApi.get(projectId);
      return researchApi.create(projectId, {
        type: "product_research",
        objective: `Research the selected product variant for ${fresh.goal}`.slice(0, 2000),
        request_key: `product-${crypto.randomUUID()}`,
        expected_version: fresh.revision,
        selected_project_product_ids: [projectProductId],
        budgets: {},
        manual_queries: null,
      });
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["research-runs", projectId] });
      void queryClient.invalidateQueries({ queryKey: ["product-research", projectId, projectProductId] });
    },
  });
  const claim = useQuery({
    queryKey: ["claim-detail", projectId, selection?.id],
    queryFn: ({ signal }) => researchApi.claim(projectId, selection!.id, signal),
    enabled: selection?.kind === "claim",
    retry: false,
  });
  const source = useQuery({
    queryKey: ["source-detail", projectId, selection?.id],
    queryFn: ({ signal }) => researchApi.source(projectId, selection!.id, signal),
    enabled: selection?.kind === "source",
    retry: false,
  });
  useEffect(() => {
    if (selection) closeButton.current?.focus();
    else opener.current?.focus();
  }, [selection]);
  useEffect(() => {
    if (!selection) return;
    function escape(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setSelection(null);
      }
    }
    window.addEventListener("keydown", escape);
    return () => window.removeEventListener("keydown", escape);
  }, [selection]);
  function inspect(kind: EvidenceSelection["kind"], id: string) {
    opener.current = document.activeElement as HTMLElement;
    setSelection({ kind, id });
  }
  function close() {
    setSelection(null);
  }

  return <section className="card product-research-card" aria-labelledby="product-research-title">
    <p className="eyebrow">Project-relative evidence</p>
    <h2 id="product-research-title">Research and fit</h2>
    {project.isError && <p role="alert">{readableError(project.error)}</p>}
    {evidence.isPending && <p role="status">Loading research…</p>}
    {evidence.isError && <p role="alert">{readableError(evidence.error)} <button type="button" onClick={() => void evidence.refetch()}>Retry</button></p>}
    {activeRun && <p role="status">Research {activeRun.status}: {activeRun.targets?.find((target) => target.project_product_id === projectProductId)?.sources_retrieved ?? 0} sources retrieved, {activeRun.targets?.find((target) => target.project_product_id === projectProductId)?.claims_created ?? 0} claims saved.</p>}
    {activeRun && runDetail.data?.stages.filter((stage) => !stage.target_project_product_id || stage.target_project_product_id === projectProductId).map((stage, index) => <p className="quiet-state" key={`${stage.stage}-${stage.source_snapshot_id ?? "plan"}-${index}`}>{stage.stage}: {stage.status}{stage.error_code ? ` (${stage.error_code})` : ""}{stage.validation_warnings.length ? ` · ${stage.validation_warnings.length} validation warnings` : ""}</p>)}
    {latestRun && !activeRun && ["failed", "partial", "interrupted"].includes(latestRun.status) && <p className="notice">Latest research {latestRun.status}: {latestRun.summary ?? latestRun.error_code ?? "Some source work did not finish."}</p>}
    {runs.isError && <p role="alert">Research progress could not load. <button type="button" onClick={() => void runs.refetch()}>Retry</button></p>}
    {evidence.data && <>
      {evidence.data.state === "no_research" && <p>No research has been run for this selected variant.</p>}
      {evidence.data.state === "no_evidence" && <p>Research returned no useful grounded claims for this variant.</p>}
      {evidence.data.state === "blocked" && <p>Source pages were blocked or could not be retrieved. The attempts remain below for inspection.</p>}
      {evidence.data.state === "partial" && <p>Partial research: some source attempts did not succeed.</p>}
      {evidence.data.assessments[0] && <>
        {evidence.data.assessments[0].context_stale && <p className="notice">Project requirements or product identity changed after this assessment. Run fresh research to reassess fit.</p>}
        <p className="quiet-state">Assessment based on saved project requirements at revision {evidence.data.assessments[0].project_revision}.</p>
        <ul className="research-conclusions">{evidence.data.assessments[0].conclusions.map((item, index) => {
          const label = typeof item.requirement_label === "string" ? item.requirement_label : "Requirement";
          const status = typeof item.status === "string" ? item.status : "unknown";
          const rationale = typeof item.rationale === "string" ? item.rationale : "Evidence is unavailable.";
          const ids = Array.isArray(item.claim_ids) ? item.claim_ids.filter((id): id is string => typeof id === "string") : [];
          return <li key={index}><strong>{label}: {status}</strong><p>{rationale}</p>{ids.map((id) => <button key={id} className="evidence-link" type="button" onClick={() => inspect("claim", id)}>Inspect cited claim</button>)}</li>;
        })}</ul>
      </>}
      <h3>Attributed claims</h3>
      {evidence.data.claims.length === 0 && <p className="quiet-state">No validated source claims yet.</p>}
      <ul className="research-claims">{evidence.data.claims.map((item) => <li key={item.id}>
        <strong>{item.evidence_category.replaceAll("_", " ")}</strong>: “{item.assertion_text}”
        <p>{item.source_title ?? "Untitled source"} · {dateLabel(item.published_at)} · {item.freshness}</p>
        <button className="evidence-link" type="button" onClick={() => inspect("claim", item.id)}>Inspect exact quote</button>
      </li>)}</ul>
      <h3>Source attempts</h3>
      {evidence.data.sources.length === 0 && <p className="quiet-state">No source pages have been attempted.</p>}
      <ul className="research-sources">{evidence.data.sources.map((item) => <li key={item.id}>
        <span>{item.title ?? item.publisher ?? "Source"} · {item.classification.replaceAll("_", " ")} · {item.status}</span>
        {item.reason && <small>Reason: {item.reason}</small>}
        {item.snapshot_id && <button className="evidence-link" type="button" onClick={() => inspect("source", item.snapshot_id!)}>Inspect source excerpt</button>}
        {safeUrl(item.final_url) && <a href={safeUrl(item.final_url)} target="_blank" rel="noopener noreferrer">Open source<span className="sr-only"> (opens in a new tab)</span></a>}
      </li>)}</ul>
    </>}
    <button className="button" type="button" disabled={Boolean(activeRun) || create.isPending || project.isPending || project.isError} onClick={() => create.mutate()}>
      {create.isPending ? "Starting research…" : evidence.data?.assessments.length ? "Run fresh research" : "Research this variant"}
    </button>
    {create.isError && <p role="alert">{create.error instanceof ApiRequestError && create.error.status === 409 ? "The project changed or another run is active. Refresh and try again." : readableError(create.error)}</p>}
    {selection && <div className="evidence-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) close(); }}>
      <aside className="evidence-panel" role="dialog" aria-modal="true" aria-label="Evidence inspection" onKeyDown={(event) => {
        if (event.key !== "Tab") return;
        const focusable = Array.from(event.currentTarget.querySelectorAll<HTMLElement>("button, a[href], [tabindex]:not([tabindex='-1'])")).filter((element) => !element.hasAttribute("disabled"));
        if (focusable.length === 0) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
      }}>
        <button ref={closeButton} className="button quiet-button evidence-close" type="button" onClick={close}>Close evidence</button>
        {selection.kind === "claim" && <>
          {claim.isPending && <p role="status">Loading claim…</p>}
          {claim.isError && <p role="alert">{readableError(claim.error)} <button type="button" onClick={() => void claim.refetch()}>Retry</button></p>}
          {claim.data && <><h2>{claim.data.attribute_key.replaceAll("_", " ")}</h2><p>Source assertion · {claim.data.evidence_category.replaceAll("_", " ")}</p><blockquote>“{claim.data.evidence_excerpt}”</blockquote><p>{claim.data.source_title ?? "Untitled source"} · {dateLabel(claim.data.published_at)} · Retrieved {new Date(claim.data.retrieved_at).toLocaleString()} · {claim.data.freshness}</p><p>Recorded context: {JSON.stringify(claim.data.qualifiers)}</p><p>Content version: {claim.data.content_hash}</p>{claim.data.relations.map((relation) => <p key={relation.related_claim_id}>Related claim: {relation.relation.replaceAll("_", " ")} · {relation.basis} <button className="evidence-link" type="button" onClick={() => inspect("claim", relation.related_claim_id)}>Inspect related claim</button></p>)}{safeUrl(claim.data.source_url) && <a href={safeUrl(claim.data.source_url)} target="_blank" rel="noopener noreferrer">Open source</a>}</>}
        </>}
        {selection.kind === "source" && <>
          {source.isPending && <p role="status">Loading source excerpt…</p>}
          {source.isError && <p role="alert">{readableError(source.error)} <button type="button" onClick={() => void source.refetch()}>Retry</button></p>}
          {source.data && <><h2>{source.data.title ?? "Source excerpt"}</h2><p>{source.data.classification.replaceAll("_", " ")} · {dateLabel(source.data.published_at)} · Retrieved {new Date(source.data.retrieved_at).toLocaleString()}</p><blockquote>{source.data.excerpt || "No retained text excerpt."}</blockquote><p>Content version: {source.data.content_hash}</p>{source.data.claims.map((item) => <button key={item.id} className="evidence-link" type="button" onClick={() => inspect("claim", item.id)}>Inspect “{item.assertion_text}”</button>)}{safeUrl(source.data.final_url) && <a href={safeUrl(source.data.final_url)} target="_blank" rel="noopener noreferrer">Open source</a>}</>}
        </>}
      </aside>
    </div>}
  </section>;
}
