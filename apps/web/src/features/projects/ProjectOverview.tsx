import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { ApiRequestError, Project, Requirement, projectsApi } from "../../api/client";
import { AssistantPanel } from "../assistant/AssistantPanel";
import { invalidateProjectWorkspace } from "../assistant/workspace-cache";
import { FieldError, NewRequirement, RequirementEditor } from "./RequirementEditor";
import { ProjectNavigation } from "./ProjectNavigation";
import { ProjectPreferenceSuggestions } from "../preferences/ProjectPreferenceSuggestions";
import {
  CURRENCIES,
  displayProjectValue,
  fieldErrors,
  fromProject,
  projectPatch,
  readableError,
  reconcileProjectDraft,
  type ConflictChoice,
  type ProjectDraft,
  type ProjectField,
  PROJECT_FIELDS,
  PROJECT_FIELD_LABELS,
} from "./projectDrafts";

export function ProjectOverview() {
  const { projectId } = useParams();
  return <ProjectOverviewContent key={projectId ?? "missing"} projectId={projectId} />;
}

function ProjectOverviewContent({ projectId }: { projectId?: string }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const headingRef = useRef<HTMLHeadingElement>(null);
  const hasFocusedHeading = useRef(false);
  const [draft, setDraft] = useState<ProjectDraft | null>(null);
  const [saveError, setSaveError] = useState("");
  const [saveMessage, setSaveMessage] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [conflict, setConflict] = useState<{ base: Project; latest: Project | null } | null>(null);
  const [conflictChoices, setConflictChoices] = useState<Partial<Record<ProjectField, ConflictChoice>>>({});
  const [requirementResetKey, setRequirementResetKey] = useState(0);
  const [knownRequirements, setKnownRequirements] = useState<Requirement[]>([]);
  const [dirtyRequirementDrafts, setDirtyRequirementDrafts] = useState<Set<string>>(
    () => new Set(),
  );
  const [proposalActionPending, setProposalActionPending] = useState(false);

  const reportRequirementDraftState = useCallback((key: string, dirty: boolean) => {
    setDirtyRequirementDrafts((current) => {
      if (current.has(key) === dirty) return current;
      const next = new Set(current);
      if (dirty) next.add(key);
      else next.delete(key);
      return next;
    });
  }, []);

  const projectQuery = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => projectsApi.get(projectId!),
    enabled: Boolean(projectId),
    retry: false,
    refetchOnWindowFocus: false,
  });
  const project = projectQuery.data;
  const draftRef = useRef(draft);
  draftRef.current = draft;

  useEffect(() => {
    hasFocusedHeading.current = false;
    setDraft(null);
    setConflict(null);
    setConflictChoices({});
    setKnownRequirements([]);
  }, [projectId]);

  useEffect(() => {
    if (project && !draft) setDraft(fromProject(project));
  }, [project, draft]);

  const assignProjectHeading = (element: HTMLHeadingElement | null) => {
    headingRef.current = element;
    if (project && element && !hasFocusedHeading.current) {
      element.focus();
      hasFocusedHeading.current = true;
    }
  };

  useEffect(() => {
    if (project) {
      setKnownRequirements((current) => {
        const currentIds = new Set(project.requirements.map((item) => item.id));
        return [...project.requirements, ...current.filter((item) => !currentIds.has(item.id))];
      });
    }
  }, [project]);

  async function reportWriteError(
    error: unknown,
    fallback: string,
    attemptedProject?: Project,
  ): Promise<Project | null> {
    if (error instanceof ApiRequestError && error.status === 409 && projectId) {
      const baseProject = attemptedProject ?? projectQuery.data;
      if (!baseProject) {
        setSaveError("The latest project version could not be loaded. Retry the refresh before continuing.");
        return null;
      }
      setSaveError("");
      setSaveMessage("");
      setConflict({ base: baseProject, latest: null });
      setConflictChoices({});
      const refreshed = await projectQuery.refetch();
      const latest = refreshed.isSuccess ? refreshed.data : undefined;
      if (latest && latest.revision > baseProject.revision) {
        const local = draftRef.current ?? fromProject(baseProject);
        const merged = reconcileProjectDraft(fromProject(baseProject), local, fromProject(latest));
        setDraft(merged.draft);
        setConflict({ base: baseProject, latest });
        return latest;
      }
      setSaveError("The latest project version could not be loaded. Retry the refresh before continuing.");
      return null;
    }
    setSaveError(error instanceof Error ? error.message : fallback);
    setErrors(fieldErrors(error));
    return null;
  }

  function acceptProjectUpdate(updated: Project) {
    if (!projectId) return;
    queryClient.setQueryData(["project", projectId], updated);
    void invalidateProjectWorkspace(queryClient, projectId, { invalidateProject: false });
    setKnownRequirements((current) => {
      const currentIds = new Set(updated.requirements.map((item) => item.id));
      return [...updated.requirements, ...current.filter((item) => !currentIds.has(item.id))];
    });
    void queryClient.invalidateQueries({ queryKey: ["projects"] });
    setConflict(null);
    setConflictChoices({});
    setSaveError("");
    setSaveMessage(`Saved revision ${updated.revision}.`);
  }

  function acceptContextProjectUpdate(updated: Project) {
    acceptProjectUpdate(updated);
    setDraft(fromProject(updated));
    setErrors({});
  }

  function acceptAssistantProjectUpdate(updated: Project, replayed: boolean) {
    if (replayed) {
      void projectQuery.refetch();
      if (projectId) void invalidateProjectWorkspace(queryClient, projectId);
      return;
    }
    acceptProjectUpdate(updated);
    setDraft(fromProject(updated));
    setErrors({});
  }

  const saveProject = useMutation({
    mutationFn: ({ baseProject, localDraft }: { baseProject: Project; localDraft: ProjectDraft }) =>
      projectsApi.patch(projectId!, projectPatch(localDraft, fromProject(baseProject), baseProject.revision)),
    onSuccess: (updated) => {
      acceptProjectUpdate(updated);
      setDraft(fromProject(updated));
      setErrors({});
    },
    onError: (error, variables) => reportWriteError(error, "Project changes could not be saved.", variables.baseProject),
  });

  const deleteProject = useMutation({
    mutationFn: ({ baseProject }: { baseProject: Project }) => projectsApi.delete(projectId!, baseProject.revision),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["projects"] });
      navigate("/");
    },
    onError: (error, variables) => reportWriteError(error, "Project could not be deleted.", variables.baseProject),
  });

  function submitProject(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (
      !project || !draft || conflict || saveProject.isPending || deleteProject.isPending ||
      proposalActionPending
    ) return;
    setSaveError("");
    setSaveMessage("");
    setErrors({});
    saveProject.mutate({ baseProject: project, localDraft: draft });
  }

  function updateDraft(field: keyof ProjectDraft, value: string) {
    setDraft((current) => (current ? { ...current, [field]: value } : current));
    setConflictChoices((current) => {
      const next = { ...current };
      delete next[field];
      return next;
    });
    setErrors((current) => ({ ...current, [field]: "" }));
    setSaveError("");
    setSaveMessage("");
  }

  function confirmDelete() {
    if (!project || conflict || proposalActionPending) return;
    const confirmed = window.confirm(
      `Delete “${project.title}”? It will disappear from your project list and cannot be restored.`,
    );
    if (confirmed) deleteProject.mutate({ baseProject: project });
  }

  function finishReconciliation() {
    if (!conflict?.latest || !draft) return;
    const resolved = reconcileProjectDraft(
      fromProject(conflict.base),
      draft,
      fromProject(conflict.latest),
      conflictChoices,
    );
    if (resolved.conflicts.length) return;
    setDraft(resolved.draft);
    setConflict(null);
    setConflictChoices({});
    setSaveError("");
  }

  function discardDraftForLatest() {
    if (!conflict?.latest) return;
    setDraft(fromProject(conflict.latest));
    setKnownRequirements(conflict.latest.requirements);
    setRequirementResetKey((current) => current + 1);
    setConflict(null);
    setConflictChoices({});
    setSaveError("");
  }

  async function refreshConflict() {
    if (!conflict) return;
    const refreshed = await projectQuery.refetch();
    const latest = refreshed.isSuccess ? refreshed.data : undefined;
    if (!latest || latest.revision <= conflict.base.revision) {
      setSaveError("The latest project version could not be loaded. Retry the refresh before continuing.");
      return;
    }
    const local = draftRef.current ?? fromProject(conflict.base);
    const merged = reconcileProjectDraft(fromProject(conflict.base), local, fromProject(latest));
    setDraft(merged.draft);
    setConflict({ base: conflict.base, latest });
    setConflictChoices({});
    setSaveError("");
  }

  if (projectQuery.isPending) {
    return <main className="shell loading-page"><p role="status">Loading project…</p></main>;
  }
  if (projectQuery.isError && projectQuery.error instanceof ApiRequestError && projectQuery.error.status === 404) {
    return (
      <main className="shell state-page">
        <div className="state-icon" aria-hidden="true">↗</div>
        <p className="eyebrow">Project unavailable</p>
        <h1 tabIndex={-1} ref={headingRef}>This project can’t be opened.</h1>
        <p>It may have been deleted or moved out of your project list.</p>
        <Link className="button primary-button button-link" to="/">Return to projects</Link>
      </main>
    );
  }
  if (projectQuery.isError && !project) {
    return (
      <main className="shell state-page">
        <p className="eyebrow">Connection issue</p>
        <h1 tabIndex={-1} ref={headingRef}>Your project did not load.</h1>
        <p role="alert">{readableError(projectQuery.error)}</p>
        <button className="button primary-button" type="button" onClick={() => void projectQuery.refetch()}>
          Retry loading project
        </button>
        <Link to="/" className="back-link">Back to projects</Link>
      </main>
    );
  }
  if (!project || !draft || !projectId) return null;

  const isDirty = Object.keys(projectPatch(draft, fromProject(project), project.revision)).length > 1;
  const conflictPreview = conflict?.latest
    ? reconcileProjectDraft(fromProject(conflict.base), draft, fromProject(conflict.latest), conflictChoices)
    : null;
  const conflictChangedFields = conflict?.latest && draft
    ? PROJECT_FIELDS.filter((field) => {
        const base = fromProject(conflict.base)[field];
        return base !== draft[field] || base !== fromProject(conflict.latest!)[field];
      })
    : [];
  const saveDisabled = saveProject.isPending || proposalActionPending || Boolean(conflict) || !isDirty;
  const renderedRequirements = [...knownRequirements].sort((left, right) => {
    const leftPosition = project.requirements.findIndex((item) => item.id === left.id);
    const rightPosition = project.requirements.findIndex((item) => item.id === right.id);
    return (leftPosition < 0 ? Number.MAX_SAFE_INTEGER : leftPosition) -
      (rightPosition < 0 ? Number.MAX_SAFE_INTEGER : rightPosition);
  });

  return (
    <main className="shell overview-shell">
      <header className="app-header">
        <Link className="brand" to="/" aria-label="Shopping Assistant home">
          <span className="brand-mark" aria-hidden="true">S</span>
          <span>Shopping Assistant</span>
        </Link>
        <div className="header-links">
          <Link className="header-back" to="/profile">Shopping Profile</Link>
          <Link className="header-back" to="/">All projects <span aria-hidden="true">↗</span></Link>
        </div>
      </header>

      <nav aria-label="Breadcrumb" className="breadcrumbs">
        <Link to="/">Projects</Link><span aria-hidden="true">/</span><span>{project.title}</span>
      </nav>
      <ProjectNavigation projectId={project.id} />

      <section className="overview-title-row">
        <div>
          <p className="eyebrow">Project overview <span className="revision-label">Revision {project.revision}</span></p>
          <h1 ref={assignProjectHeading} tabIndex={-1}>{project.title}</h1>
          <p className="overview-lede">A clear place for your goal, requirements, and budget.</p>
        </div>
        <div className="project-title-actions">
          <Link className="button secondary-button" to={`/projects/${project.id}/discover`}>
            Discover products
          </Link>
          <span className={`status-pill status-${project.status}`}>{project.status}</span>
        </div>
      </section>

      {projectQuery.isError && (
        <p className="notice error-notice" role="alert">
          The latest project version could not refresh. Your current entries are still available.
        </p>
      )}

      <ProjectPreferenceSuggestions
        project={project}
        blocked={Boolean(conflict) || isDirty || saveProject.isPending || deleteProject.isPending || proposalActionPending}
        onProjectUpdate={acceptContextProjectUpdate}
      />

      {conflict && (
        <section className="notice conflict-notice" role="alert" aria-labelledby="conflict-title">
          <div>
            <p className="eyebrow">Another edit was saved</p>
            <h2 id="conflict-title">Reconcile your draft with revision {conflict.latest?.revision ?? "…"}</h2>
            {conflict.latest ? (
              <>
                <p>Unchanged fields use the latest saved values. Your edits to other fields stay in the form.</p>
                {conflictChangedFields.length > 0 && (
                  <ul className="conflict-differences">
                    {conflictChangedFields.map((field) => {
                      const baseValue = fromProject(conflict.base)[field];
                      const latestValue = fromProject(conflict.latest!)[field];
                      const localValue = draft[field];
                      const overlaps = baseValue !== localValue && baseValue !== latestValue && localValue !== latestValue;
                      return (
                        <li key={field}>
                          <strong>{PROJECT_FIELD_LABELS[field]}</strong>
                          <span>Latest saved: {displayProjectValue(latestValue)}</span>
                          <span>Your draft: {displayProjectValue(localValue)}</span>
                          {overlaps && (
                            <div className="conflict-field-actions" aria-label={`Choose ${PROJECT_FIELD_LABELS[field]}`}>
                              <button
                                className="button small-button quiet-button"
                                type="button"
                                aria-pressed={conflictChoices[field] === "mine"}
                                onClick={() => setConflictChoices((current) => ({ ...current, [field]: "mine" }))}
                              >Keep my {PROJECT_FIELD_LABELS[field].toLowerCase()}</button>
                              <button
                                className="button small-button quiet-button"
                                type="button"
                                aria-pressed={conflictChoices[field] === "latest"}
                                onClick={() => setConflictChoices((current) => ({ ...current, [field]: "latest" }))}
                              >Use latest {PROJECT_FIELD_LABELS[field].toLowerCase()}</button>
                            </div>
                          )}
                        </li>
                      );
                    })}
                  </ul>
                )}
                <p>
                  Requirements at the rejected revision: {conflict.base.requirements.map((item) => item.label).join(" · ") || "None"}.
                  Latest requirements: {conflict.latest.requirements.map((item) => item.label).join(" · ") || "None"}.
                </p>
              </>
            ) : (
              <>
                <p>Your entries are preserved. The latest version has not loaded, so saving and deletion are paused.</p>
                <button className="button quiet-button" type="button" onClick={() => void refreshConflict()}>
                  Retry loading latest version
                </button>
              </>
            )}
          </div>
          {conflict.latest && (
            <div className="conflict-actions">
              <button
                className="button secondary-button"
                type="button"
                disabled={Boolean(conflictPreview?.conflicts.length)}
                onClick={finishReconciliation}
              >Apply reconciled draft</button>
              <button className="button quiet-button" type="button" onClick={discardDraftForLatest}>
                Discard drafts and use latest
              </button>
            </div>
          )}
        </section>
      )}

      <div className="overview-grid">
        <section className="card overview-card" aria-labelledby="details-title">
          <div className="section-heading">
            <span className="step-mark" aria-hidden="true">01</span>
            <div>
              <p className="eyebrow">The shape of your search</p>
              <h2 id="details-title">Project details</h2>
            </div>
          </div>
          <form onSubmit={submitProject}>
            <fieldset
              className="pending-fieldset"
              disabled={saveProject.isPending || deleteProject.isPending || proposalActionPending}
            >
              <legend className="sr-only">Project details</legend>
            <div className="field-grid">
              <div className="field-span-two">
                <label className="field-label" htmlFor="overview-title">Project name</label>
                <input
                  id="overview-title"
                  value={draft.title}
                  maxLength={200}
                  required
                  aria-invalid={Boolean(errors.title)}
                  aria-describedby={errors.title ? "overview-title-error" : undefined}
                  onChange={(event) => updateDraft("title", event.target.value)}
                />
                <FieldError id="overview-title-error" message={errors.title} />
              </div>
              <div className="field-span-two">
                <label className="field-label" htmlFor="overview-goal">Goal</label>
                <textarea
                  id="overview-goal"
                  value={draft.goal}
                  rows={4}
                  maxLength={4000}
                  required
                  aria-invalid={Boolean(errors.goal)}
                  aria-describedby={errors.goal ? "overview-goal-error" : undefined}
                  onChange={(event) => updateDraft("goal", event.target.value)}
                />
                <FieldError id="overview-goal-error" message={errors.goal} />
              </div>
              <div>
                <label className="field-label" htmlFor="overview-category">Category <span className="optional">Optional</span></label>
                <input
                  id="overview-category"
                  value={draft.category}
                  maxLength={100}
                  onChange={(event) => updateDraft("category", event.target.value)}
                />
                <FieldError id="overview-category-error" message={errors.category} />
              </div>
              <div>
                <label className="field-label" htmlFor="overview-status">Project status</label>
                <select
                  id="overview-status"
                  value={draft.status}
                  onChange={(event) => updateDraft("status", event.target.value as Project["status"])}
                >
                  <option value="active">Active</option>
                  <option value="completed">Completed</option>
                  <option value="archived">Archived</option>
                </select>
              </div>
              <div className="field-span-two">
                <label className="field-label" htmlFor="overview-notes">Notes <span className="optional">Optional</span></label>
                <textarea
                  id="overview-notes"
                  value={draft.notes}
                  rows={4}
                  maxLength={10000}
                  aria-invalid={Boolean(errors.notes)}
                  aria-describedby={errors.notes ? "overview-notes-error" : undefined}
                  onChange={(event) => updateDraft("notes", event.target.value)}
                />
                <FieldError id="overview-notes-error" message={errors.notes} />
              </div>
            </div>

            <div className="budget-section">
              <div>
                <p className="eyebrow">Set a comfortable range</p>
                <h3>Budget</h3>
              </div>
              <div className="budget-fields">
                <div>
                  <label className="field-label" htmlFor="budget-target">Target <span className="optional">Optional</span></label>
                  <input
                    id="budget-target"
                    inputMode="decimal"
                    value={draft.budgetTarget}
                    placeholder="300.00"
                    onChange={(event) => updateDraft("budgetTarget", event.target.value)}
                  />
                  <FieldError id="budget-target-error" message={errors.budget_target} />
                </div>
                <div>
                  <label className="field-label" htmlFor="budget-maximum">Maximum <span className="optional">Optional</span></label>
                  <input
                    id="budget-maximum"
                    inputMode="decimal"
                    value={draft.budgetMaximum}
                    placeholder="400.00"
                    onChange={(event) => updateDraft("budgetMaximum", event.target.value)}
                  />
                  <FieldError id="budget-maximum-error" message={errors.budget_maximum} />
                </div>
                <div>
                  <label className="field-label" htmlFor="budget-currency">Currency</label>
                  <select
                    id="budget-currency"
                    value={draft.budgetCurrency}
                    onChange={(event) => updateDraft("budgetCurrency", event.target.value)}
                  >
                    <option value="">Choose</option>
                    {CURRENCIES.map((currency) => <option key={currency} value={currency}>{currency}</option>)}
                  </select>
                  <FieldError id="budget-currency-error" message={errors.budget_currency} />
                </div>
              </div>
              <p className="field-help">Enter amounts to the cent. A currency is required whenever either amount is set.</p>
            </div>

            {saveError && <p className="notice error-notice" role="alert">{saveError}</p>}
            {saveMessage && <p className="save-message" role="status">{saveMessage}</p>}
            <div className="form-actions">
              <button className="button primary-button" type="submit" disabled={saveDisabled}>
                {saveProject.isPending ? "Saving changes…" : "Save changes"}
              </button>
              {conflict && <span className="field-help">Apply the reconciled draft before continuing.</span>}
            </div>
            </fieldset>
          </form>
        </section>

        <section className="card requirements-card" aria-labelledby="requirements-title">
          <div className="section-heading">
            <span className="step-mark" aria-hidden="true">02</span>
            <div>
              <p className="eyebrow">What matters for this purchase</p>
              <h2 id="requirements-title">Requirements</h2>
            </div>
            <span className="count-pill">{project.requirements.length}</span>
          </div>
          {project.requirements.length === 0 && (
            <p className="quiet-state">Add a must-have, preference, or constraint when you’re ready.</p>
          )}
          <ol className="requirement-list">
            {renderedRequirements.map((requirement) => {
              const latestRequirement = project.requirements.find((item) => item.id === requirement.id);
              const index = latestRequirement?.position ?? requirement.position;
              return (
              <RequirementEditor
                key={`${requirement.id}-${requirementResetKey}`}
                project={project}
                requirement={requirement}
                latestRequirement={latestRequirement}
                index={index}
                blocked={Boolean(conflict) || deleteProject.isPending || proposalActionPending}
                onProjectUpdate={acceptProjectUpdate}
                onWriteError={reportWriteError}
                onForget={() => setKnownRequirements((current) => current.filter((item) => item.id !== requirement.id))}
                onDraftStateChange={reportRequirementDraftState}
              />
              );
            })}
          </ol>
          {project.requirements.length < 100 && (
            <NewRequirement
              key={`${project.id}-${requirementResetKey}`}
              project={project}
              blocked={Boolean(conflict) || deleteProject.isPending || proposalActionPending}
              onProjectUpdate={acceptProjectUpdate}
              onWriteError={reportWriteError}
              onDraftStateChange={reportRequirementDraftState}
            />
          )}
        </section>
      </div>

      <section className="danger-zone" aria-labelledby="delete-title">
        <div>
          <p className="eyebrow">Project lifecycle</p>
          <h2 id="delete-title">Delete this project</h2>
          <p>Archived projects can be restored by changing their status. Deleted projects disappear from your list.</p>
        </div>
        <button className="button danger-button" type="button" disabled={deleteProject.isPending || proposalActionPending || Boolean(conflict)} onClick={confirmDelete}>
          {deleteProject.isPending ? "Deleting…" : "Delete project"}
        </button>
      </section>

      <AssistantPanel
        key={project.id}
        project={project}
        blocked={
          Boolean(conflict) ||
          isDirty ||
          dirtyRequirementDrafts.size > 0 ||
          saveProject.isPending ||
          deleteProject.isPending ||
          proposalActionPending
        }
        onProjectUpdate={acceptAssistantProjectUpdate}
        onRevisionConflict={(error) => reportWriteError(error, "The assistant proposal could not be applied.", project)}
        onProposalActionPendingChange={setProposalActionPending}
      />
    </main>
  );
}
