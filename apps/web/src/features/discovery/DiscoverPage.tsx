import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";

import {
  ApiRequestError,
  ResearchCreate,
  ResearchRunRead,
  projectsApi,
  researchApi,
} from "../../api/client";
import { catalogApi } from "../../api/client";
import { CatalogCandidateActions } from "./CatalogCandidateActions";
import { ProjectNavigation } from "../projects/ProjectNavigation";
import { ProductDecisionActions } from "../decisions/ProductDecisionActions";
import { ProjectAssistant } from "../assistant/ProjectAssistant";

type SavedCommand = { command: ResearchCreate; requestKey: string };
const TERMINAL = new Set<ResearchRunRead["status"]>([
  "succeeded",
  "partial",
  "failed",
  "canceled",
  "interrupted",
]);

function requestStorageKey(projectId: string) {
  return `shopping-assistant:discovery-command:${projectId}`;
}

function readSavedCommand(projectId: string): SavedCommand | null {
  try {
    const saved = window.sessionStorage.getItem(requestStorageKey(projectId));
    if (!saved) return null;
    const value: unknown = JSON.parse(saved);
    if (!isSavedCommand(value)) {
      window.sessionStorage.removeItem(requestStorageKey(projectId));
      return null;
    }
    return value;
  } catch {
    return null;
  }
}

function writeSavedCommand(projectId: string, saved: SavedCommand | null) {
  try {
    if (saved) window.sessionStorage.setItem(requestStorageKey(projectId), JSON.stringify(saved));
    else window.sessionStorage.removeItem(requestStorageKey(projectId));
  } catch {
    // The form still works when browser storage is unavailable.
  }
}

function isSavedCommand(value: unknown): value is SavedCommand {
  if (!value || typeof value !== "object") return false;
  const saved = value as Partial<SavedCommand>;
  const command = saved.command;
  if (
    typeof saved.requestKey !== "string" ||
    saved.requestKey.length < 8 ||
    saved.requestKey.length > 100 ||
    !command ||
    typeof command !== "object" ||
    command.type !== "discovery" ||
    typeof command.objective !== "string" ||
    !command.objective.trim() ||
    command.objective.length > 2000 ||
    command.request_key !== saved.requestKey ||
    !Number.isInteger(command.expected_version) ||
    command.expected_version < 1
  ) {
    return false;
  }
  if (command.manual_queries !== undefined) {
    if (
      !Array.isArray(command.manual_queries) ||
      command.manual_queries.length < 1 ||
      command.manual_queries.length > 20 ||
      command.manual_queries.some(
        (query) => typeof query !== "string" || !query.trim() || query.length > 300,
      )
    ) {
      return false;
    }
  }
  return true;
}

function newRequestKey() {
  return globalThis.crypto?.randomUUID?.() ?? `discovery-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function readableError(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback;
}

function safeOutboundUrl(value: string): string | undefined {
  try {
    const url = new URL(value);
    if (!["http:", "https:"].includes(url.protocol) || url.username || url.password) {
      return undefined;
    }
    return url.href;
  } catch {
    return undefined;
  }
}

export function DiscoverPage() {
  const { projectId } = useParams();
  return <DiscoverPageContent key={projectId ?? "missing"} projectId={projectId} />;
}

function DiscoverPageContent({ projectId }: { projectId?: string }) {
  const queryClient = useQueryClient();
  const headingRef = useRef<HTMLHeadingElement>(null);
  const pollingCount = useRef(0);
  const submittingRef = useRef(false);
  const [isVisible, setIsVisible] = useState(() => document.visibilityState === "visible");
  const [savedCommand, setSavedCommand] = useState<SavedCommand | null>(() =>
    projectId ? readSavedCommand(projectId) : null,
  );
  const [objective, setObjective] = useState(() => savedCommand?.command.objective ?? "");
  const [manualMode, setManualMode] = useState(() =>
    Boolean(savedCommand?.command.manual_queries),
  );
  const [manualQueries, setManualQueries] = useState(
    () => savedCommand?.command.manual_queries?.join("\n") ?? "",
  );
  const [submitError, setSubmitError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [cancelError, setCancelError] = useState("");

  useEffect(() => {
    const updateVisibility = () => setIsVisible(document.visibilityState === "visible");
    document.addEventListener("visibilitychange", updateVisibility);
    return () => document.removeEventListener("visibilitychange", updateVisibility);
  }, []);

  const projectQuery = useQuery({
    queryKey: ["project", projectId],
    queryFn: ({ signal }) => projectsApi.get(projectId!, signal),
    enabled: Boolean(projectId),
    retry: false,
    refetchOnWindowFocus: false,
  });
  const project = projectQuery.data;

  const objectiveInitialized = useRef(false);
  useEffect(() => {
    if (project && !objectiveInitialized.current) {
      if (!savedCommand) setObjective(project.goal);
      objectiveInitialized.current = true;
    }
  }, [project, savedCommand]);

  useEffect(() => {
    headingRef.current?.focus();
  }, [projectId]);

  const runsQuery = useInfiniteQuery({
    queryKey: ["research-runs", projectId],
    initialPageParam: undefined as string | undefined,
    queryFn: ({ signal, pageParam }) => researchApi.list(projectId!, 20, pageParam, signal),
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    enabled: Boolean(projectId && project),
    retry: false,
    refetchOnWindowFocus: false,
    refetchInterval: (query) => {
      const active = query.state.data?.pages.some((page) =>
        page.items.some((run) => !TERMINAL.has(run.status)),
      );
      if (!isVisible || !active) {
        if (!active) pollingCount.current = 0;
        return false;
      }
      const pause = Math.min(1200 * 2 ** pollingCount.current, 10000);
      pollingCount.current += 1;
      return pause;
    },
  });
  const runs = runsQuery.data?.pages.flatMap((page) => page.items) ?? [];
  const currentRunId = selectedRunId ?? runs[0]?.id ?? null;
  const detailQuery = useQuery({
    queryKey: ["research-run", projectId, currentRunId],
    queryFn: ({ signal }) => researchApi.get(projectId!, currentRunId!, signal),
    enabled: Boolean(projectId && currentRunId),
    retry: false,
    refetchOnWindowFocus: false,
    refetchInterval: (query) => {
      const run = query.state.data;
      if (!isVisible || !run || TERMINAL.has(run.status)) return false;
      return 1300;
    },
  });
  const candidatesQuery = useInfiniteQuery({
    queryKey: ["discovery-candidates", projectId, currentRunId],
    initialPageParam: undefined as string | undefined,
    queryFn: ({ signal, pageParam }) =>
      researchApi.candidates(projectId!, currentRunId!, 20, pageParam, signal),
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    enabled: Boolean(projectId && currentRunId),
    retry: false,
    refetchOnWindowFocus: false,
    refetchInterval: () => {
      const run = detailQuery.data;
      return isVisible && run?.id === currentRunId && !TERMINAL.has(run.status) ? 4000 : false;
    },
  });
  const projectProductsQuery = useInfiniteQuery({
    queryKey: ["project-products", projectId],
    initialPageParam: undefined as string | undefined,
    queryFn: ({ signal, pageParam }) =>
      catalogApi.listProjectProducts(projectId!, 20, pageParam, signal),
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    enabled: Boolean(projectId && project),
    retry: false,
    refetchOnWindowFocus: false,
  });

  const currentRun = detailQuery.data?.id === currentRunId ? detailQuery.data : undefined;
  const candidateRefreshKey = currentRun
    ? `${currentRun.id}:${currentRun.status}:${currentRun.results_found}:${currentRun.candidates_found}`
    : "";
  const lastCandidateRefresh = useRef("");
  useEffect(() => {
    if (!projectId || !currentRunId || !candidateRefreshKey) return;
    if (lastCandidateRefresh.current === candidateRefreshKey) return;
    lastCandidateRefresh.current = candidateRefreshKey;
    void queryClient.invalidateQueries({
      queryKey: ["discovery-candidates", projectId, currentRunId],
    });
  }, [candidateRefreshKey, currentRunId, projectId, queryClient]);

  const cancelRun = useMutation({
    mutationFn: (runId: string) => researchApi.cancel(projectId!, runId),
    onSuccess: async (result) => {
      setCancelError("");
      queryClient.setQueryData(["research-run", projectId, result.run.id], result.run);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["research-runs", projectId] }),
        queryClient.invalidateQueries({
          queryKey: ["discovery-candidates", projectId, result.run.id],
        }),
      ]);
    },
    onError: (error) => setCancelError(readableError(error, "The run could not be canceled.")),
  });

  async function submit(event?: FormEvent<HTMLFormElement>, replaySaved = false) {
    event?.preventDefault();
    if (!projectId || !project || submittingRef.current) return;
    let pending = replaySaved ? savedCommand : null;
    if (!pending) {
      const queries = manualQueries
        .split("\n")
        .map((line) => line.trim())
        .filter(Boolean);
      const command: ResearchCreate = {
        objective: objective.trim(),
        type: "discovery",
        request_key: newRequestKey(),
        expected_version: project.revision,
        ...(manualMode ? { manual_queries: queries } : {}),
      };
      pending = { command, requestKey: command.request_key };
      setSavedCommand(pending);
      writeSavedCommand(projectId, pending);
    }
    submittingRef.current = true;
    setSubmitting(true);
    setSubmitError("");
    try {
      const result = await researchApi.create(projectId, pending.command);
      writeSavedCommand(projectId, null);
      setSavedCommand(null);
      setSelectedRunId(result.run_id);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["research-runs", projectId] }),
        queryClient.invalidateQueries({ queryKey: ["research-run", projectId, result.run_id] }),
        queryClient.invalidateQueries({
          queryKey: ["discovery-candidates", projectId, result.run_id],
        }),
      ]);
    } catch (error) {
      const knownPreacceptanceError =
        error instanceof ApiRequestError &&
        (error.status === 400 ||
          error.status === 409 ||
          error.status === 422 ||
          (error.status === 503 &&
            ["research_capacity", "research_unavailable"].includes(error.code)));
      if (knownPreacceptanceError) {
        writeSavedCommand(projectId, null);
        setSavedCommand(null);
      }
      if (error instanceof ApiRequestError && error.code === "revision_conflict") {
        const refreshed = await projectQuery.refetch();
        setSubmitError(
          refreshed.isError
            ? "The project changed, and its latest revision could not load. Your entries are still here; retry loading the project before starting again."
            : "The project changed. Its latest revision is loaded, and your entries are still here. Review them and start again with a new request.",
        );
      } else {
        setSubmitError(
          error instanceof ApiRequestError && knownPreacceptanceError
            ? `${error.message} Your entries are still here.`
            : "The response was not received. Retry the same request to safely check whether it started.",
        );
      }
    } finally {
      submittingRef.current = false;
      setSubmitting(false);
    }
  }

  if (!projectId) return null;
  if (projectQuery.isPending) {
    return <main className="shell loading-page"><p role="status">Loading project…</p></main>;
  }
  if (projectQuery.isError || !project) {
    const missing = projectQuery.error instanceof ApiRequestError && projectQuery.error.status === 404;
    return (
      <main className="shell state-page">
        <p className="eyebrow">{missing ? "Project unavailable" : "Connection issue"}</p>
        <h1 tabIndex={-1} ref={headingRef}>
          {missing ? "This project can’t be opened." : "Discovery could not load the project."}
        </h1>
        <p role="alert">{readableError(projectQuery.error, "Try loading the project again.")}</p>
        {!missing && (
          <button className="button primary-button" type="button" onClick={() => void projectQuery.refetch()}>
            Retry loading project
          </button>
        )}
        <Link className="back-link" to="/">Return to projects</Link>
      </main>
    );
  }

  const visibleCandidates = candidatesQuery.data?.pages.flatMap((page) => page.items) ?? [];
  const normalizedProducts = projectProductsQuery.data?.pages.flatMap((page) => page.items) ?? [];
  const catalogVersion = projectProductsQuery.data?.pages[0]?.catalog_version;
  const active = Boolean(currentRun && !TERMINAL.has(currentRun.status));
  const controlsLocked = Boolean(savedCommand || cancelRun.isPending);

  return (
    <main className="shell discover-shell">
      <header className="app-header">
        <Link className="brand" to="/" aria-label="Shopping Assistant home">
          <span className="brand-mark" aria-hidden="true">S</span>
          <span>Shopping Assistant</span>
        </Link>
        <Link className="header-back" to={`/projects/${project.id}`}>Project overview</Link>
      </header>

      <nav aria-label="Breadcrumb" className="breadcrumbs">
        <Link to="/">Projects</Link><span aria-hidden="true">/</span>
        <Link to={`/projects/${project.id}`}>{project.title}</Link><span aria-hidden="true">/</span>
        <span>Discover</span>
      </nav>
      <ProjectNavigation projectId={project.id} />

      <section className="discover-title-row">
        <div>
          <p className="eyebrow">Project discovery · Snapshot revision {project.revision}</p>
          <h1 ref={headingRef} tabIndex={-1}>Explore options for {project.title}</h1>
          <p className="overview-lede">Search observations stay provisional until product details are researched.</p>
        </div>
        <Link className="button quiet-button" to={`/projects/${project.id}`}>Edit project details</Link>
      </section>

      <section className="discover-layout">
        <div className="discover-main-column">
          <section className="card discovery-form-card" aria-labelledby="start-discovery-title">
            <div className="section-heading">
              <span className="step-mark" aria-hidden="true">01</span>
              <div>
                <p className="eyebrow">Start with saved requirements</p>
                <h2 id="start-discovery-title">Plan a product search</h2>
              </div>
            </div>

            <div className="project-context-summary">
              <div>
                <span className="field-label">Goal</span>
                <p>{project.goal}</p>
              </div>
              <div className="context-budget">
                <span className="field-label">Budget</span>
                <p>
                  {project.budget_maximum
                    ? `Up to ${project.budget_maximum} ${project.budget_currency}`
                    : project.budget_target
                      ? `Target ${project.budget_target} ${project.budget_currency}`
                      : "Not specified"}
                </p>
              </div>
              <div className="field-span-two">
                <span className="field-label">Requirements</span>
                {project.requirements.length ? (
                  <ul className="context-requirements">
                    {project.requirements.map((requirement) => (
                      <li key={requirement.id}>
                        <span className={`requirement-kind requirement-kind-${requirement.kind}`}>
                          {requirement.kind.replace("_", " ")}
                        </span>
                        <span>{requirement.label}</span>
                        {requirement.detail && <small>{requirement.detail}</small>}
                      </li>
                    ))}
                  </ul>
                ) : <p>No saved requirements yet. <Link to={`/projects/${project.id}`}>Add them in project details.</Link></p>}
              </div>
            </div>

            <form onSubmit={(event) => void submit(event)}>
              <fieldset className="pending-fieldset" disabled={controlsLocked || cancelRun.isPending}>
                <legend className="sr-only">Discovery request</legend>
                <label className="field-label" htmlFor="discovery-objective">What would you like to find?</label>
                <textarea
                  id="discovery-objective"
                  value={objective}
                  onChange={(event) => setObjective(event.target.value)}
                  rows={3}
                  maxLength={2000}
                  required
                />
                <label className="discovery-mode">
                  <input
                    type="checkbox"
                    checked={manualMode}
                    onChange={(event) => setManualMode(event.target.checked)}
                  />
                  <span>Enter exact search queries myself</span>
                </label>
                {manualMode && (
                  <div>
                    <label className="field-label" htmlFor="manual-queries">Search queries <span className="optional">One per line</span></label>
                    <textarea
                      id="manual-queries"
                      value={manualQueries}
                      onChange={(event) => setManualQueries(event.target.value)}
                      maxLength={6000}
                      rows={4}
                      placeholder={'cordless vacuum pet hair under $400 USD\nquiet upright vacuum for apartment'}
                      required
                    />
                  </div>
                )}
              </fieldset>

              {submitError && <p className="notice error-notice discovery-error" role="alert">{submitError}</p>}
              {savedCommand ? (
                <div className="saved-command-notice" role="status">
                  <p>A request with this exact key may already be running.</p>
                  <button
                    className="button secondary-button"
                    type="button"
                    disabled={submitting || cancelRun.isPending}
                    onClick={() => void submit(undefined, true)}
                  >
                    {submitting ? "Checking request…" : "Retry the same request"}
                  </button>
                </div>
              ) : (
                <button className="button primary-button discovery-start" type="submit" disabled={submitting || cancelRun.isPending}>
                  {submitting ? "Starting discovery…" : "Start discovery"}
                </button>
              )}
              <p className="field-help">The project revision is captured when this run starts. Search activity does not change project requirements.</p>
            </form>
          </section>

          <section className="card discovery-results-card" aria-labelledby="candidate-title">
            <div className="section-heading">
              <span className="step-mark muted-mark" aria-hidden="true">02</span>
              <div>
                <p className="eyebrow">Search result observations</p>
                <h2 id="candidate-title">Candidates</h2>
              </div>
              <span className="count-pill">{visibleCandidates.length}</span>
            </div>
            {candidatesQuery.isPending && currentRunId && <p role="status">Loading search observations…</p>}
            {candidatesQuery.isError && (
              <div className="empty-state compact-empty">
                <h3>Candidate observations did not load.</h3>
                <p role="alert">{readableError(candidatesQuery.error, "Try again in a moment.")}</p>
                <button className="button quiet-button" type="button" onClick={() => void candidatesQuery.refetch()}>Retry candidates</button>
              </div>
            )}
            {!candidatesQuery.isError && visibleCandidates.length === 0 && (
              <div className="empty-state compact-empty">
                <span className="empty-icon" aria-hidden="true">⌕</span>
                <h3>{active ? "Search is in progress." : currentRun ? "No candidates found for this run." : "No discovery runs yet."}</h3>
                <p>{active ? "Results appear as each query finishes." : "Start a search to collect provisional product links and snippets."}</p>
              </div>
            )}
            <ul className="candidate-list">
              {visibleCandidates.map((candidate) => (
                <li className="candidate-card" key={candidate.id}>
                  <div className="candidate-card-heading">
                    <div>
                      <p className="eyebrow">
                        {candidate.normalization?.product_id ? "Catalog product" : "Search observation"}
                      </p>
                      <h3>{candidate.provisional_name}</h3>
                    </div>
                    {!candidate.normalization?.product_id && (
                      <span className="candidate-badge">Provisional · not yet matched</span>
                    )}
                  </div>
                  <p className="candidate-reason">{candidate.discovery_reason}</p>
                  {candidate.indicative_price_text && (
                    <p className="candidate-price-text">Unverified price text: {candidate.indicative_price_text}</p>
                  )}
                  {candidate.search_results.map((result) => (
                    <article className="candidate-observation" key={result.search_result_id}>
                      <p className="observation-origin">Found for “{result.query_text}” · observed {new Date(result.received_at).toLocaleString()}</p>
                      {result.snippet && <p className="candidate-snippet">{result.snippet}</p>}
                      {safeOutboundUrl(result.url) ? (
                        <a href={safeOutboundUrl(result.url)} target="_blank" rel="noopener noreferrer">
                          {result.title || result.url}<span className="sr-only"> (opens in a new tab)</span>
                        </a>
                      ) : <p className="quiet-state">Source link unavailable.</p>}
                    </article>
                  ))}
                  <CatalogCandidateActions
                    projectId={project.id}
                    candidate={candidate}
                    projectVersion={project.revision}
                    catalogVersion={catalogVersion}
                  />
                </li>
              ))}
            </ul>
            {candidatesQuery.hasNextPage && (
              <button
                className="button quiet-button"
                type="button"
                disabled={candidatesQuery.isFetchingNextPage}
                onClick={() => void candidatesQuery.fetchNextPage()}
              >
                {candidatesQuery.isFetchingNextPage ? "Loading more candidates…" : "Load more candidates"}
              </button>
            )}

            <section className="project-catalog-section" aria-labelledby="project-catalog-title">
              <div className="section-heading compact-section-heading">
                <div>
                  <p className="eyebrow">Exact project variants</p>
                  <h3 id="project-catalog-title">Normalized products</h3>
                </div>
                <span className="count-pill">{normalizedProducts.length}</span>
              </div>
              {projectProductsQuery.isPending && <p role="status">Loading this project’s catalog…</p>}
              {projectProductsQuery.isError && (
                <div className="empty-state compact-empty">
                  <p role="alert">{readableError(projectProductsQuery.error, "The project catalog could not load.")}</p>
                  <button className="button quiet-button" type="button" onClick={() => void projectProductsQuery.refetch()}>Retry catalog</button>
                </div>
              )}
              {!projectProductsQuery.isPending && !projectProductsQuery.isError && normalizedProducts.length === 0 && (
                <p className="quiet-state">No candidates have been linked to products yet.</p>
              )}
              {normalizedProducts.length > 0 && (
                <ul className="normalized-product-list">
                  {normalizedProducts.map((item) => (
                    <li key={item.id}>
                      <div className="normalized-product-identity">
                        <Link to={`/products/${item.product_id}?${new URLSearchParams({ variant: item.variant_id, project: projectId!, project_product: item.id }).toString()}`}>{item.canonical_name}</Link>
                        <p>{[item.brand, item.model_family, item.variant_name].filter(Boolean).join(" · ")}</p>
                        <ProductDecisionActions project={project} projectProductId={item.id} />
                      </div>
                      <span>{item.offers.length} recent {item.offers.length === 1 ? "offer" : "offers"}</span>
                    </li>
                  ))}
                </ul>
              )}
              {projectProductsQuery.hasNextPage && (
                <button className="button quiet-button" type="button" disabled={projectProductsQuery.isFetchingNextPage} onClick={() => void projectProductsQuery.fetchNextPage()}>
                  {projectProductsQuery.isFetchingNextPage ? "Loading products…" : "Load more products"}
                </button>
              )}
            </section>
          </section>
        </div>

        <aside className="discover-side-column">
          <section className="card run-card" aria-labelledby="run-title">
            <div className="section-heading">
              <span className="step-mark muted-mark" aria-hidden="true">03</span>
              <div>
                <p className="eyebrow">Durable run progress</p>
                <h2 id="run-title">Discovery run</h2>
              </div>
            </div>
            {runsQuery.isError && (
              <div className="notice error-notice">
                <p role="alert">{readableError(runsQuery.error, "Run history did not load.")}</p>
                <button className="button quiet-button" type="button" onClick={() => void runsQuery.refetch()}>Retry run history</button>
              </div>
            )}
            {detailQuery.isError && (
              <div className="notice error-notice" role="alert">
                The selected run could not refresh. <button className="button small-button quiet-button" type="button" onClick={() => void detailQuery.refetch()}>Retry</button>
              </div>
            )}
            {currentRun ? (
              <RunProgress
                run={currentRun}
                cancelling={cancelRun.isPending}
                cancelError={cancelError}
                onCancel={() => cancelRun.mutate(currentRun.id)}
              />
            ) : !runsQuery.isError ? (
              <p className="quiet-state">Your searches and progress will appear here.</p>
            ) : null}
          </section>

          <section className="card run-history-card" aria-labelledby="history-title">
            <div className="section-heading recent-heading">
              <div>
                <p className="eyebrow">Saved across reloads</p>
                <h2 id="history-title">Run history</h2>
              </div>
            </div>
            {runs.length === 0 && !runsQuery.isPending && !runsQuery.isError && (
              <p className="quiet-state">No saved runs yet.</p>
            )}
            <ul className="run-history-list">
              {runs.map((run) => (
                <li key={run.id}>
                  <button
                    className={`run-history-item${run.id === currentRunId ? " run-history-item-selected" : ""}`}
                    type="button"
                    aria-current={run.id === currentRunId ? "true" : undefined}
                    onClick={() => setSelectedRunId(run.id)}
                  >
                    <span className={`run-status status-${run.status}`}>{run.status}</span>
                    <strong>{run.objective}</strong>
                    <small>{run.candidates_found} candidates · {run.queries_completed}/{run.queries_planned} queries complete</small>
                  </button>
                </li>
              ))}
            </ul>
            {runsQuery.hasNextPage && (
              <button
                className="button quiet-button"
                type="button"
                disabled={runsQuery.isFetchingNextPage}
                onClick={() => void runsQuery.fetchNextPage()}
              >
                {runsQuery.isFetchingNextPage ? "Loading older runs…" : "Load older runs"}
              </button>
            )}
          </section>
        </aside>
      </section>
      <ProjectAssistant project={project} />
    </main>
  );
}

function RunProgress({
  run,
  cancelling,
  cancelError,
  onCancel,
}: {
  run: ResearchRunRead;
  cancelling: boolean;
  cancelError: string;
  onCancel: () => void;
}) {
  const queries = run.queries ?? [];
  return (
    <div className="run-progress">
      <div className="run-status-row">
        <span className={`run-status status-${run.status}`}>{run.status}</span>
        <span>Project revision {run.snapshot_revision}</span>
      </div>
      <p className="run-objective">{run.objective}</p>
      <dl className="run-counters">
        <div><dt>Queries</dt><dd>{run.queries_completed} / {run.queries_planned}</dd></div>
        <div><dt>Attempts</dt><dd>{run.attempts_used} / {run.effective_budgets.max_attempts}</dd></div>
        <div><dt>Results</dt><dd>{run.results_found} / {run.effective_budgets.max_results}</dd></div>
        <div><dt>Candidates</dt><dd>{run.candidates_found} / {run.effective_budgets.max_candidates}</dd></div>
        {run.queries_failed > 0 && <div><dt>Failed queries</dt><dd>{run.queries_failed}</dd></div>}
        {run.skipped_count > 0 && <div><dt>Skipped work</dt><dd>{run.skipped_count}</dd></div>}
      </dl>
      {run.summary && <p className="run-summary">{run.summary}</p>}
      {run.error_code && <p className="run-error-code">Error: {run.error_code.replaceAll("_", " ")}</p>}
      {queries.length > 0 && (
        <ol className="query-progress-list">
          {queries.map((query) => (
            <li key={query.id}>
              <div>
                <strong>{query.text}</strong>
                <span className={`query-state query-state-${query.state}`}>{query.state}</span>
              </div>
              {query.error_code && <small>{query.error_code.replaceAll("_", " ")}</small>}
            </li>
          ))}
        </ol>
      )}
      {!TERMINAL.has(run.status) && (
        <button className="button danger-button cancel-run-button" type="button" disabled={cancelling} onClick={onCancel}>
          {cancelling ? "Canceling discovery…" : "Cancel discovery"}
        </button>
      )}
      {cancelError && <p className="field-error" role="alert">{cancelError}</p>}
      <p className="run-timestamp">Started {run.started_at ? new Date(run.started_at).toLocaleString() : "waiting for the local worker"}</p>
    </div>
  );
}
