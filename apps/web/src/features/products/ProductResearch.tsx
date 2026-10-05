import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { ApiRequestError, ResearchCreate, projectsApi, researchApi } from "../../api/client";

type EvidenceSelection = { kind: "claim" | "source"; id: string };
type SavedProductCommand = { command: ResearchCreate; requestKey: string };

function commandStorageKey(projectId: string, projectProductId: string) {
  return `shopping-assistant:product-research-command:${projectId}:${projectProductId}`;
}

function readCommand(key: string): SavedProductCommand | null {
  try {
    const raw = window.sessionStorage.getItem(key);
    if (!raw) return null;
    const value: unknown = JSON.parse(raw);
    if (!value || typeof value !== "object") throw new Error("Invalid command");
    const saved = value as Partial<SavedProductCommand>;
    const command = saved.command;
    if (!command || command.type !== "product_research" ||
      typeof saved.requestKey !== "string" || saved.requestKey.length < 8 || saved.requestKey.length > 100 ||
      command.request_key !== saved.requestKey || !Number.isInteger(command.expected_version) ||
      command.expected_version < 1 || typeof command.objective !== "string" || !command.objective.trim() ||
      command.objective.length > 2000 || !Array.isArray(command.selected_project_product_ids) ||
      command.selected_project_product_ids.length !== 1) throw new Error("Invalid command");
    return saved as SavedProductCommand;
  } catch {
    try { window.sessionStorage.removeItem(key); } catch { /* storage unavailable */ }
    return null;
  }
}

function writeCommand(key: string, value: SavedProductCommand | null) {
  try {
    if (value) window.sessionStorage.setItem(key, JSON.stringify(value));
    else window.sessionStorage.removeItem(key);
  } catch { /* storage unavailable */ }
}

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
  const storageKey = commandStorageKey(projectId, projectProductId);
  const [savedCommand, setSavedCommand] = useState<SavedProductCommand | null>(() => readCommand(storageKey));
  const [selectedAssessment, setSelectedAssessment] = useState(0);
  const [assessmentOffset, setAssessmentOffset] = useState(0);
  const [claimOffset, setClaimOffset] = useState(0);
  const [sourceOffset, setSourceOffset] = useState(0);
  const [selectedRunId, setSelectedRunId] = useState<string | undefined>();
  const [isVisible, setIsVisible] = useState(document.visibilityState === "visible");
  const pollStartedAt = useRef(Date.now());
  const opener = useRef<HTMLElement | null>(null);
  const closeButton = useRef<HTMLButtonElement | null>(null);
  const dialogRef = useRef<HTMLElement | null>(null);
  const isDialogOpen = selection !== null;
  const project = useQuery({
    queryKey: ["project", projectId],
    queryFn: ({ signal }) => projectsApi.get(projectId, signal),
    retry: false,
  });
  const evidence = useQuery({
    queryKey: ["product-research", projectId, projectProductId, assessmentOffset, selectedRunId, claimOffset, sourceOffset],
    queryFn: ({ signal }) => researchApi.productEvidence(projectId, projectProductId, assessmentOffset, selectedRunId, claimOffset, sourceOffset, signal),
    retry: false,
    refetchInterval: (query) => isVisible &&
      Date.now() - pollStartedAt.current < 360_000 &&
      ["queued", "running"].includes(query.state.data?.latest_run_status ?? "") ? 4000 : false,
  });
  const activeRun = ["queued", "running"].includes(evidence.data?.latest_run_status ?? "");
  const latestRunId = evidence.data?.latest_run_id;
  const runDetail = useQuery({
    queryKey: ["research-run-detail", projectId, latestRunId],
    queryFn: ({ signal }) => researchApi.get(projectId, latestRunId!, signal),
    enabled: Boolean(latestRunId),
    retry: false,
    refetchInterval: () => isVisible && activeRun && Date.now() - pollStartedAt.current < 360_000 ? 4000 : false,
  });
  useEffect(() => {
    if (
      ["succeeded", "partial", "failed", "interrupted", "canceled"].includes(
        runDetail.data?.status ?? "",
      ) && ["queued", "running"].includes(evidence.data?.latest_run_status ?? "")
    ) {
      void queryClient.invalidateQueries({
        queryKey: ["product-research", projectId, projectProductId],
      });
    }
  }, [
    evidence.data?.latest_run_status,
    projectId,
    projectProductId,
    queryClient,
    runDetail.data?.status,
  ]);
  const create = useMutation({
    mutationFn: async () => {
      let pending = savedCommand;
      if (!pending) {
        const fresh = await projectsApi.get(projectId);
        const command: ResearchCreate = {
          type: "product_research",
          objective: `Research the selected product variant for ${fresh.goal}`.slice(0, 2000),
          request_key: `product-${crypto.randomUUID()}`,
          expected_version: fresh.revision,
          selected_project_product_ids: [projectProductId],
          budgets: {},
          manual_queries: null,
        };
        pending = { command, requestKey: command.request_key };
        setSavedCommand(pending);
        writeCommand(storageKey, pending);
      }
      return researchApi.create(projectId, pending.command);
    },
    onSuccess: () => {
      pollStartedAt.current = Date.now();
      writeCommand(storageKey, null);
      setSavedCommand(null);
      void queryClient.invalidateQueries({ queryKey: ["research-runs", projectId] });
      void queryClient.invalidateQueries({ queryKey: ["product-research", projectId, projectProductId] });
    },
    onError: (error) => {
      if (error instanceof ApiRequestError && [400, 409, 422].includes(error.status)) {
        writeCommand(storageKey, null);
        setSavedCommand(null);
        void queryClient.invalidateQueries({ queryKey: ["project", projectId] });
        void queryClient.invalidateQueries({ queryKey: ["product-research", projectId, projectProductId] });
        void queryClient.invalidateQueries({ queryKey: ["research-runs", projectId] });
      }
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
  useEffect(() => {
    if (!isDialogOpen || !dialogRef.current) return;
    const previouslyInert = new Map<HTMLElement, boolean>();
    let child: HTMLElement = dialogRef.current;
    const root = document.getElementById("root");
    while (child.parentElement && child.parentElement !== root) {
      const parent = child.parentElement;
      for (const sibling of Array.from(parent.children)) {
        if (!(sibling instanceof HTMLElement) || sibling === child) continue;
        previouslyInert.set(sibling, sibling.inert);
        sibling.inert = true;
      }
      child = parent;
    }
    return () => {
      for (const [element, wasInert] of previouslyInert) element.inert = wasInert;
    };
  }, [isDialogOpen]);
  useEffect(() => {
    pollStartedAt.current = Date.now();
    setAssessmentOffset(0);
    setClaimOffset(0);
    setSourceOffset(0);
    setSelectedAssessment(0);
    setSelectedRunId(undefined);
    setSavedCommand(readCommand(storageKey));
    const updateVisibility = () => setIsVisible(document.visibilityState === "visible");
    document.addEventListener("visibilitychange", updateVisibility);
    return () => document.removeEventListener("visibilitychange", updateVisibility);
  }, [projectId, projectProductId, storageKey]);
  function inspect(kind: EvidenceSelection["kind"], id: string) {
    if (!selection) opener.current = document.activeElement as HTMLElement;
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
    {activeRun && <p role="status">Research {evidence.data?.latest_run_status}: {runDetail.data?.targets?.find((target) => target.project_product_id === projectProductId)?.sources_retrieved ?? 0} sources retrieved, {runDetail.data?.targets?.find((target) => target.project_product_id === projectProductId)?.claims_created ?? 0} claims saved.</p>}
    {activeRun && Date.now() - pollStartedAt.current >= 360_000 && <p role="status">Automatic updates paused. <button type="button" onClick={() => { pollStartedAt.current = Date.now(); void evidence.refetch(); void runDetail.refetch(); }}>Refresh progress</button></p>}
    {(runDetail.data?.stages ?? []).filter((stage) => !stage.target_project_product_id || stage.target_project_product_id === projectProductId).map((stage, index) => <p className="quiet-state" key={`${stage.stage}-${stage.source_snapshot_id ?? "plan"}-${index}`}>{stage.stage}: {stage.status}{stage.error_code ? ` (${stage.error_code})` : ""}{stage.validation_warnings.length ? ` · ${stage.validation_warnings.length} validation warnings` : ""}</p>)}
    {!activeRun && evidence.data?.latest_run_status === "succeeded" && <p className="quiet-state">Latest research completed: {runDetail.data?.summary ?? "Source review finished."}</p>}
    {!activeRun && ["failed", "partial", "interrupted", "canceled"].includes(evidence.data?.latest_run_status ?? "") && <p className="notice">Latest research {evidence.data?.latest_run_status}: {runDetail.data?.summary ?? runDetail.data?.error_code ?? "Some source work did not finish."}</p>}
    {runDetail.isError && <p role="alert">Research progress could not load. <button type="button" onClick={() => void runDetail.refetch()}>Retry</button></p>}
    {evidence.data && <>
      {!activeRun && evidence.data.state === "no_research" && <p>No research has been run for this selected variant.</p>}
      {!activeRun && evidence.data.state === "no_evidence" && <p>Research returned no useful grounded claims for this variant.</p>}
      {!activeRun && evidence.data.state === "blocked" && <p>Source pages were blocked or could not be retrieved. The attempts remain below for inspection.</p>}
      {!activeRun && evidence.data.state === "partial" && <p>Partial research: some source attempts did not succeed.</p>}
      {evidence.data.assessments[selectedAssessment] && <>
        <label>Assessment history <select value={selectedAssessment} onChange={(event) => { const index = Number(event.target.value); setSelectedAssessment(index); setSelectedRunId(evidence.data!.assessments[index]?.research_run_id); setClaimOffset(0); setSourceOffset(0); }}>{evidence.data.assessments.map((item, index) => <option key={item.id} value={index}>{new Date(item.generated_at).toLocaleString()} · revision {item.project_revision}</option>)}</select></label>
        {evidence.data.assessments[selectedAssessment].context_stale && <p className="notice">Project requirements or product identity changed after this assessment. Run fresh research to reassess fit.</p>}
        <p className="quiet-state">Assessment based on saved project requirements at revision {evidence.data.assessments[selectedAssessment].project_revision}.</p>
        <ul className="research-conclusions">{evidence.data.assessments[selectedAssessment].conclusions.map((item, index) => {
          const label = typeof item.requirement_label === "string" ? item.requirement_label : "Requirement";
          const status = typeof item.status === "string" ? item.status : "unknown";
          const rationale = typeof item.rationale === "string" ? item.rationale : "Evidence is unavailable.";
          const ids = Array.isArray(item.claim_ids) ? item.claim_ids.filter((id): id is string => typeof id === "string") : [];
          return <li key={index}><strong>{label}: {status}</strong><p>{rationale}</p>{ids.map((id) => <button key={id} className="evidence-link" type="button" onClick={() => inspect("claim", id)}>Inspect cited claim</button>)}</li>;
        })}</ul>
      </>}
      {(assessmentOffset > 0 || evidence.data.has_more_assessments) && <nav aria-label="Assessment history pages">
        {assessmentOffset > 0 && <button type="button" onClick={() => { setAssessmentOffset(Math.max(0, assessmentOffset - 20)); setSelectedAssessment(0); setSelectedRunId(undefined); setClaimOffset(0); setSourceOffset(0); }}>Newer assessments</button>}
        {evidence.data.has_more_assessments && <button type="button" onClick={() => { setAssessmentOffset(assessmentOffset + 20); setSelectedAssessment(0); setSelectedRunId(undefined); setClaimOffset(0); setSourceOffset(0); }}>Older assessments</button>}
      </nav>}
      <h3>Attributed claims</h3>
      {evidence.data.claims.length === 0 && <p className="quiet-state">No validated source claims yet.</p>}
      <ul className="research-claims">{evidence.data.claims.map((item) => <li key={item.id}>
        <strong>{item.evidence_category.replaceAll("_", " ")}</strong>: “{item.assertion_text}”
        <p>{item.source_title ?? "Untitled source"} · {dateLabel(item.published_at)} · {item.freshness}</p>
        <button className="evidence-link" type="button" onClick={() => inspect("claim", item.id)}>Inspect exact quote</button>
      </li>)}</ul>
      {(claimOffset > 0 || evidence.data.has_more_claims) && <nav aria-label="Claim pages">
        {claimOffset > 0 && <button type="button" onClick={() => setClaimOffset(Math.max(0, claimOffset - 20))}>Newer claims</button>}
        {evidence.data.has_more_claims && <button type="button" onClick={() => setClaimOffset(claimOffset + 20)}>Older claims</button>}
      </nav>}
      <h3>Source attempts</h3>
      {evidence.data.sources.length === 0 && <p className="quiet-state">No source pages have been attempted.</p>}
      <ul className="research-sources">{evidence.data.sources.map((item) => <li key={item.id}>
        <span>{item.title ?? item.publisher ?? "Source"} · {item.classification.replaceAll("_", " ")} · {item.status}</span>
        {item.classification_basis && <small>Classification basis: {item.classification_basis}</small>}
        {item.reason && <small>Reason: {item.reason}</small>}
        {item.snapshot_id && <button className="evidence-link" type="button" onClick={() => inspect("source", item.snapshot_id!)}>Inspect source excerpt</button>}
        {safeUrl(item.final_url) && <a href={safeUrl(item.final_url)} target="_blank" rel="noopener noreferrer">Open source<span className="sr-only"> (opens in a new tab)</span></a>}
      </li>)}</ul>
      {(sourceOffset > 0 || evidence.data.has_more_sources) && <nav aria-label="Source attempt pages">
        {sourceOffset > 0 && <button type="button" onClick={() => setSourceOffset(Math.max(0, sourceOffset - 20))}>Newer source attempts</button>}
        {evidence.data.has_more_sources && <button type="button" onClick={() => setSourceOffset(sourceOffset + 20)}>Older source attempts</button>}
      </nav>}
    </>}
    <button className="button" type="button" disabled={Boolean(activeRun) || create.isPending || project.isPending || project.isError} onClick={() => create.mutate()}>
      {create.isPending ? "Starting research…" : savedCommand ? "Retry research request" : evidence.data?.assessments.length ? "Run fresh research" : "Research this variant"}
    </button>
    {create.isError && <p role="alert">{create.error instanceof ApiRequestError && create.error.status === 409 ? "The project changed or another run is active. Refresh and try again." : readableError(create.error)}</p>}
    {selection && <div className="evidence-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) close(); }}>
      <aside ref={dialogRef} className="evidence-panel" role="dialog" aria-modal="true" aria-label="Evidence inspection" onKeyDown={(event) => {
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
          {claim.data && <><h2>{claim.data.attribute_key.replaceAll("_", " ")}</h2><p>Source assertion · {claim.data.evidence_category.replaceAll("_", " ")}</p><blockquote>“{claim.data.evidence_excerpt}”</blockquote><p>{claim.data.source_title ?? "Untitled source"} · {dateLabel(claim.data.published_at)} · Retrieved {new Date(claim.data.retrieved_at).toLocaleString()} · {claim.data.freshness}</p>{Object.entries(claim.data.qualifiers).length > 0 && <dl>{Object.entries(claim.data.qualifiers).map(([key, value]) => <div key={key}><dt>{key.replaceAll("_", " ")}</dt><dd>{String(value)}</dd></div>)}</dl>}{claim.data.relations.map((relation) => <p key={relation.related_claim_id}>Related claim: {relation.relation.replaceAll("_", " ")} · {relation.basis} <button className="evidence-link" type="button" onClick={() => inspect("claim", relation.related_claim_id)}>Inspect related claim</button></p>)}{safeUrl(claim.data.source_url) && <a href={safeUrl(claim.data.source_url)} target="_blank" rel="noopener noreferrer">Open source</a>}</>}
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
