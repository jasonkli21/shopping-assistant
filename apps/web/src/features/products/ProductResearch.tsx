import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { ApiRequestError, ResearchCreate, projectsApi, researchApi } from "../../api/client";

type EvidenceSelection = { kind: "claim" | "source"; id: string };
type SavedProductCommand = { command: ResearchCreate; requestKey: string };
type SavedProductRetry = {
  sourceRunId: string;
  command: { request_key: string; expected_version: number };
};
const SOURCE_CLASSES = [
  ["manufacturer_specification", "Manufacturer specifications"],
  ["independent_measurement", "Independent measurements"],
  ["editorial_assessment", "Professional reviews"],
  ["retailer_listing", "Retailer listings"],
  ["community_observation", "Owner discussions"],
] as const;
type SourceClass = (typeof SOURCE_CLASSES)[number][0];

function parseDomains(value: string) {
  return [...new Set(value.split(/[\s,]+/).map((item) => item.trim()).filter(Boolean))];
}

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

function retryStorageKey(projectId: string, projectProductId: string, sourceRunId: string) {
  return `shopping-assistant:product-research-retry:${projectId}:${projectProductId}:${sourceRunId}`;
}

function readRetry(key: string, sourceRunId: string): SavedProductRetry | null {
  try {
    const raw = window.sessionStorage.getItem(key);
    if (!raw) return null;
    const value: unknown = JSON.parse(raw);
    if (!value || typeof value !== "object") throw new Error("Invalid retry command");
    const saved = value as Partial<SavedProductRetry>;
    if (
      saved.sourceRunId !== sourceRunId ||
      !saved.command ||
      typeof saved.command.request_key !== "string" ||
      !Number.isInteger(saved.command.expected_version)
    ) throw new Error("Invalid retry command");
    return saved as SavedProductRetry;
  } catch {
    try { window.sessionStorage.removeItem(key); } catch { /* storage unavailable */ }
    return null;
  }
}

function writeRetry(key: string, saved: SavedProductRetry | null) {
  try {
    if (saved) window.sessionStorage.setItem(key, JSON.stringify(saved));
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
  const [researchMode, setResearchMode] = useState<"quick" | "deep">("quick");
  const [refreshTargets, setRefreshTargets] = useState<Array<"offers" | "claims">>([]);
  const [sourceClasses, setSourceClasses] = useState<SourceClass[]>(
    SOURCE_CLASSES.map(([value]) => value),
  );
  const [includeDomains, setIncludeDomains] = useState("");
  const [excludeDomains, setExcludeDomains] = useState("");
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
      void Promise.all([
        queryClient.invalidateQueries({ queryKey: ["product-research", projectId, projectProductId] }),
        queryClient.invalidateQueries({ queryKey: ["product-offers"] }),
        queryClient.invalidateQueries({ queryKey: ["product",] }),
        queryClient.invalidateQueries({ queryKey: ["project-products", projectId] }),
        queryClient.invalidateQueries({ queryKey: ["project-comparisons", projectId] }),
        queryClient.invalidateQueries({ queryKey: ["comparison", projectId] }),
      ]);
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
          mode: researchMode,
          objective: `Research the selected product variant for ${fresh.goal}`.slice(0, 2000),
          request_key: `product-${crypto.randomUUID()}`,
          expected_version: fresh.revision,
          selected_project_product_ids: [projectProductId],
          source_targets: {
            source_classes: sourceClasses,
            include_domains: parseDomains(includeDomains),
            exclude_domains: parseDomains(excludeDomains),
          },
          ...(refreshTargets.length > 0 && latestRunId ? {
            refresh_of_run_id: latestRunId,
            refresh_targets: refreshTargets,
          } : {}),
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
      setSelectedRunId(undefined);
      setSelectedAssessment(0);
      setAssessmentOffset(0);
      setClaimOffset(0);
      setSourceOffset(0);
      writeCommand(storageKey, null);
      setSavedCommand(null);
      void Promise.all([
        queryClient.invalidateQueries({ queryKey: ["research-runs", projectId] }),
        queryClient.invalidateQueries({ queryKey: ["product-research", projectId, projectProductId] }),
        queryClient.invalidateQueries({ queryKey: ["product-offers"] }),
        queryClient.invalidateQueries({ queryKey: ["product",] }),
        queryClient.invalidateQueries({ queryKey: ["project-products", projectId] }),
        queryClient.invalidateQueries({ queryKey: ["project-comparisons", projectId] }),
      ]);
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
  const cancel = useMutation({
    mutationFn: () => researchApi.cancel(projectId, latestRunId!),
    onSuccess: async ({ run }) => {
      queryClient.setQueryData(["research-run-detail", projectId, run.id], run);
      await queryClient.invalidateQueries({ queryKey: ["product-research", projectId, projectProductId] });
    },
  });
  const retry = useMutation({
    mutationFn: async (sourceRunId: string) => {
      if (!project.data) throw new Error("The saved project is unavailable.");
      const retryKey = retryStorageKey(projectId, projectProductId, sourceRunId);
      let saved = readRetry(retryKey, sourceRunId);
      if (!saved) {
        saved = {
          sourceRunId,
          command: {
            request_key: `product-retry-${crypto.randomUUID()}`,
            expected_version: project.data.revision,
          },
        };
        writeRetry(retryKey, saved);
      }
      return researchApi.retry(projectId, sourceRunId, saved.command);
    },
    onSuccess: async (_result, sourceRunId) => {
      writeRetry(retryStorageKey(projectId, projectProductId, sourceRunId), null);
      pollStartedAt.current = Date.now();
      setSelectedRunId(undefined);
      setSelectedAssessment(0);
      setAssessmentOffset(0);
      setClaimOffset(0);
      setSourceOffset(0);
      await queryClient.invalidateQueries({ queryKey: ["product-research", projectId, projectProductId] });
      await queryClient.invalidateQueries({ queryKey: ["research-runs", projectId] });
      await queryClient.invalidateQueries({ queryKey: ["product-offers"] });
      await queryClient.invalidateQueries({ queryKey: ["project-products", projectId] });
    },
    onError: async (error, sourceRunId) => {
      const retryKey = retryStorageKey(projectId, projectProductId, sourceRunId);
      if (error instanceof ApiRequestError && [400, 404, 409, 422, 503].includes(error.status)) {
        writeRetry(retryKey, null);
      }
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["project", projectId] }),
        queryClient.invalidateQueries({ queryKey: ["product-research", projectId, projectProductId] }),
        queryClient.invalidateQueries({ queryKey: ["research-runs", projectId] }),
      ]);
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
    setRefreshTargets([]);
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
    <fieldset className="research-mode-options" disabled={Boolean(savedCommand) || Boolean(activeRun) || create.isPending}>
      <legend className="field-label">Research depth</legend>
      <label><input type="radio" name={`research-mode-${projectProductId}`} checked={researchMode === "quick"} onChange={() => setResearchMode("quick")} /><span><strong>Quick</strong> · up to 2 sources and 4 pages</span></label>
      <label><input type="radio" name={`research-mode-${projectProductId}`} checked={researchMode === "deep"} onChange={() => setResearchMode("deep")} /><span><strong>Deep</strong> · search for missing dimensions across source classes</span></label>
    </fieldset>
    <fieldset className="research-target-controls" disabled={Boolean(savedCommand) || Boolean(activeRun) || create.isPending || !latestRunId}>
      <legend className="field-label">Refresh existing evidence</legend>
      <label><input type="checkbox" checked={refreshTargets.includes("offers")} onChange={() => setRefreshTargets((current) => current.includes("offers") ? current.filter((item) => item !== "offers") : [...current, "offers"])} /><span>Current retailer offers</span></label>
      <label><input type="checkbox" checked={refreshTargets.includes("claims")} onChange={() => setRefreshTargets((current) => current.includes("claims") ? current.filter((item) => item !== "claims") : [...current, "claims"])} /><span>Specifications and product claims</span></label>
      {!latestRunId && <p className="field-help">Run research once before requesting a targeted refresh.</p>}
    </fieldset>
    <details className="research-target-controls">
      <summary>Choose source targets</summary>
      <fieldset disabled={Boolean(savedCommand) || Boolean(activeRun) || create.isPending}>
        <legend className="sr-only">Allowed source classes</legend>
        {SOURCE_CLASSES.map(([value, label]) => <label key={value}>
          <input
            type="checkbox"
            checked={sourceClasses.includes(value)}
            onChange={() => setSourceClasses((current) => current.includes(value)
              ? current.length > 1 ? current.filter((item) => item !== value) : current
              : [...current, value])}
          />
          <span>{label}</span>
        </label>)}
      </fieldset>
      <label>Include domains <span className="optional">Optional, comma or space separated</span>
        <input value={includeDomains} onChange={(event) => setIncludeDomains(event.target.value)} disabled={Boolean(savedCommand) || Boolean(activeRun) || create.isPending} placeholder="example.com" />
      </label>
      <label>Exclude domains <span className="optional">Syndication and unwanted sites</span>
        <input value={excludeDomains} onChange={(event) => setExcludeDomains(event.target.value)} disabled={Boolean(savedCommand) || Boolean(activeRun) || create.isPending} placeholder="news.example.com" />
      </label>
      <p className="field-help">Domain filters apply before page retrieval. Product identity and retriever safety checks still apply.</p>
    </details>
    {project.isError && <p role="alert">{readableError(project.error)}</p>}
    {evidence.isPending && <p role="status">Loading research…</p>}
    {evidence.isError && <p role="alert">{readableError(evidence.error)} <button type="button" onClick={() => void evidence.refetch()}>Retry</button></p>}
    {activeRun && <p role="status">Research {evidence.data?.latest_run_status}: {runDetail.data?.targets?.find((target) => target.project_product_id === projectProductId)?.sources_retrieved ?? 0} sources retrieved, {runDetail.data?.targets?.find((target) => target.project_product_id === projectProductId)?.claims_created ?? 0} claims saved.</p>}
    {(runDetail.data?.jobs ?? []).map((job) => <p className="quiet-state" role="status" key={job.id}>
      {job.stage_type.replaceAll("_", " ")}: {job.status} · attempt {job.attempt_count}/{job.max_attempts}
      {job.error_code ? ` · ${job.error_code}` : ""}
      {(job.attempts ?? []).map((attempt) => attempt.error_code ? ` · attempt ${attempt.number}: ${attempt.error_code}` : "")}
    </p>)}
    {(runDetail.data?.queries ?? []).map((query) => <p className="quiet-state" key={query.id}>
      {query.text}: {query.state}{query.retry_not_before ? ` · retry ${new Date(query.retry_not_before).toLocaleTimeString()}` : ""}
      {(query.attempts ?? []).map((attempt) => ` · attempt ${attempt.attempt_number}: ${attempt.status}${attempt.error_code ? ` (${attempt.error_code})` : ""}`)}
    </p>)}
    {activeRun && <button type="button" disabled={cancel.isPending} onClick={() => cancel.mutate()}>
      {cancel.isPending ? "Canceling…" : "Cancel research"}
    </button>}
    {cancel.isError && <p role="alert">{readableError(cancel.error)}</p>}
    {runDetail.data && latestRunId && ["failed", "partial", "interrupted", "canceled"].includes(runDetail.data.status) && <button type="button" disabled={retry.isPending || project.isPending} onClick={() => retry.mutate(latestRunId)}>
      {retry.isPending ? "Retrying…" : "Retry incomplete research"}
    </button>}
    {retry.isError && <p role="alert">{readableError(retry.error)}</p>}
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
        {item.offer_status && <small>Offer refresh: {item.offer_status.replaceAll("_", " ")}{item.offer_error_code ? ` · ${item.offer_error_code.replaceAll("_", " ")}` : ""}{item.offer_observation?.amount ? ` · ${item.offer_observation.amount} ${item.offer_observation.currency ?? ""}` : ""}{item.offer_observation?.retailer_name ? ` · ${item.offer_observation.retailer_name}` : ""}</small>}
        {item.snapshot_id && <button className="evidence-link" type="button" onClick={() => inspect("source", item.snapshot_id!)}>Inspect source excerpt</button>}
        {safeUrl(item.final_url) && <a href={safeUrl(item.final_url)} target="_blank" rel="noopener noreferrer">Open source<span className="sr-only"> (opens in a new tab)</span></a>}
      </li>)}</ul>
      {(sourceOffset > 0 || evidence.data.has_more_sources) && <nav aria-label="Source attempt pages">
        {sourceOffset > 0 && <button type="button" onClick={() => setSourceOffset(Math.max(0, sourceOffset - 20))}>Newer source attempts</button>}
        {evidence.data.has_more_sources && <button type="button" onClick={() => setSourceOffset(sourceOffset + 20)}>Older source attempts</button>}
      </nav>}
    </>}
    <button className="button" type="button" disabled={Boolean(activeRun) || create.isPending || project.isPending || project.isError} onClick={() => create.mutate()}>
      {create.isPending ? "Starting research…" : savedCommand ? "Retry research request" : refreshTargets.length ? "Refresh selected evidence" : evidence.data?.assessments.length ? "Run fresh research" : "Research this variant"}
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
