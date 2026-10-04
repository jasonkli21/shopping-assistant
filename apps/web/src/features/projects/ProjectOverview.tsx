import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import {
  ApiRequestError,
  Project,
  ProjectPatch,
  Requirement,
  RequirementCreate,
  RequirementPatch,
  projectsApi,
} from "../../api/client";

type ProjectDraft = {
  title: string;
  goal: string;
  category: string;
  status: Project["status"];
  budgetTarget: string;
  budgetMaximum: string;
  budgetCurrency: string;
  notes: string;
};

type RequirementDraft = {
  kind: Requirement["kind"];
  label: string;
  detail: string;
  attributeKey: string;
  operator: NonNullable<Requirement["operator"]> | "";
  value: string;
  unit: string;
};

const CURRENCIES = ["USD", "CAD", "EUR", "GBP", "JPY", "AUD", "NZD", "CHF", "CNY", "INR"];
const REQUIREMENT_KINDS: Requirement["kind"][] = ["must_have", "preference", "constraint"];
const REQUIREMENT_OPERATORS: NonNullable<Requirement["operator"]>[] = [
  "eq",
  "gte",
  "lte",
  "contains",
  "one_of",
];

function fromProject(project: Project): ProjectDraft {
  return {
    title: project.title,
    goal: project.goal,
    category: project.category ?? "",
    status: project.status,
    budgetTarget: project.budget_target ?? "",
    budgetMaximum: project.budget_maximum ?? "",
    budgetCurrency: project.budget_currency ?? "",
    notes: project.notes ?? "",
  };
}

function fromRequirement(requirement: Requirement): RequirementDraft {
  return {
    kind: requirement.kind,
    label: requirement.label,
    detail: requirement.detail ?? "",
    attributeKey: requirement.attribute_key ?? "",
    operator: requirement.operator ?? "",
    value: requirement.value == null ? "" : JSON.stringify(requirement.value),
    unit: requirement.unit ?? "",
  };
}

function fieldErrors(error: unknown): Record<string, string> {
  if (!(error instanceof ApiRequestError) || !Array.isArray(error.details)) return {};
  return Object.fromEntries(
    error.details.flatMap((item) => {
      if (
        typeof item !== "object" ||
        item === null ||
        !("field" in item) ||
        !("message" in item) ||
        typeof item.field !== "string" ||
        typeof item.message !== "string"
      ) {
        return [];
      }
      return [[item.field.split(".").at(-1) ?? item.field, item.message]];
    }),
  );
}

function readableError(error: unknown): string {
  return error instanceof Error ? error.message : "The request could not be completed.";
}

function moneyPatch(draft: ProjectDraft, expectedVersion: number): ProjectPatch {
  const hasBudget = Boolean(draft.budgetTarget.trim() || draft.budgetMaximum.trim());
  return {
    expected_version: expectedVersion,
    title: draft.title,
    goal: draft.goal,
    category: draft.category.trim() || null,
    status: draft.status,
    budget_target: draft.budgetTarget.trim() || null,
    budget_maximum: draft.budgetMaximum.trim() || null,
    budget_currency: hasBudget ? draft.budgetCurrency || null : null,
    notes: draft.notes.trim() || null,
  };
}

function requirementBody(draft: RequirementDraft): Omit<RequirementCreate, "kind" | "label" | "detail"> {
  if (!draft.attributeKey.trim()) return {};
  if (!draft.operator || !draft.value.trim()) {
    throw new Error("Add an operator and a JSON value for the structured criterion.");
  }
  let value: unknown;
  try {
    value = JSON.parse(draft.value);
  } catch {
    throw new Error("Enter a valid JSON value, such as true, 4, \"lightweight\", or [\"one\", \"two\"].");
  }
  return {
    attribute_key: draft.attributeKey.trim(),
    operator: draft.operator,
    value,
    unit: draft.unit.trim() || null,
  };
}

export function ProjectOverview() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const headingRef = useRef<HTMLHeadingElement>(null);
  const hasFocusedHeading = useRef(false);
  const [draft, setDraft] = useState<ProjectDraft | null>(null);
  const [saveError, setSaveError] = useState("");
  const [saveMessage, setSaveMessage] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [conflictNeedsReview, setConflictNeedsReview] = useState(false);
  const [requirementResetKey, setRequirementResetKey] = useState(0);

  const projectQuery = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => projectsApi.get(projectId!),
    enabled: Boolean(projectId),
    retry: false,
    refetchOnWindowFocus: false,
  });
  const project = projectQuery.data;

  useEffect(() => {
    hasFocusedHeading.current = false;
    setDraft(null);
    setConflictNeedsReview(false);
  }, [projectId]);

  useEffect(() => {
    if (project && !draft) setDraft(fromProject(project));
    if (project && !hasFocusedHeading.current && headingRef.current) {
      headingRef.current.focus();
      hasFocusedHeading.current = true;
    }
  }, [project, draft]);

  async function reportWriteError(error: unknown, fallback: string) {
    if (error instanceof ApiRequestError && error.status === 409 && projectId) {
      setSaveError("");
      setSaveMessage("");
      setConflictNeedsReview(true);
      await queryClient.refetchQueries({ queryKey: ["project", projectId], type: "active" });
      return;
    }
    setSaveError(error instanceof Error ? error.message : fallback);
    setErrors(fieldErrors(error));
  }

  function acceptProjectUpdate(updated: Project) {
    if (!projectId) return;
    queryClient.setQueryData(["project", projectId], updated);
    void queryClient.invalidateQueries({ queryKey: ["projects"] });
    setConflictNeedsReview(false);
    setSaveError("");
    setSaveMessage(`Saved revision ${updated.revision}.`);
  }

  const saveProject = useMutation({
    mutationFn: (command: ProjectPatch) => projectsApi.patch(projectId!, command),
    onSuccess: (updated) => {
      acceptProjectUpdate(updated);
      setDraft(fromProject(updated));
      setErrors({});
    },
    onError: (error) => reportWriteError(error, "Project changes could not be saved."),
  });

  const deleteProject = useMutation({
    mutationFn: (expectedVersion: number) => projectsApi.delete(projectId!, expectedVersion),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["projects"] });
      navigate("/");
    },
    onError: (error) => reportWriteError(error, "Project could not be deleted."),
  });

  function submitProject(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!project || !draft || conflictNeedsReview) return;
    setSaveError("");
    setSaveMessage("");
    setErrors({});
    saveProject.mutate(moneyPatch(draft, project.revision));
  }

  function updateDraft(field: keyof ProjectDraft, value: string) {
    setDraft((current) => (current ? { ...current, [field]: value } : current));
    setErrors((current) => ({ ...current, [field]: "" }));
    setSaveError("");
    setSaveMessage("");
  }

  function confirmDelete() {
    if (!project || conflictNeedsReview) return;
    const confirmed = window.confirm(
      `Delete “${project.title}”? It will disappear from your project list and cannot be restored.`,
    );
    if (confirmed) deleteProject.mutate(project.revision);
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

  const isDirty = JSON.stringify(draft) !== JSON.stringify(fromProject(project));
  const saveDisabled = saveProject.isPending || conflictNeedsReview || !isDirty;

  return (
    <main className="shell overview-shell">
      <header className="app-header">
        <Link className="brand" to="/" aria-label="Shopping Assistant home">
          <span className="brand-mark" aria-hidden="true">S</span>
          <span>Shopping Assistant</span>
        </Link>
        <Link className="header-back" to="/">All projects <span aria-hidden="true">↗</span></Link>
      </header>

      <nav aria-label="Breadcrumb" className="breadcrumbs">
        <Link to="/">Projects</Link><span aria-hidden="true">/</span><span>{project.title}</span>
      </nav>

      <section className="overview-title-row">
        <div>
          <p className="eyebrow">Project overview <span className="revision-label">Revision {project.revision}</span></p>
          <h1 ref={headingRef} tabIndex={-1}>{project.title}</h1>
          <p className="overview-lede">A clear place for your goal, requirements, and budget.</p>
        </div>
        <span className={`status-pill status-${project.status}`}>{project.status}</span>
      </section>

      {projectQuery.isError && (
        <p className="notice error-notice" role="alert">
          The latest project version could not refresh. Your current entries are still available.
        </p>
      )}

      {conflictNeedsReview && (
        <section className="notice conflict-notice" role="alert" aria-labelledby="conflict-title">
          <div>
            <p className="eyebrow">Another edit was saved</p>
            <h2 id="conflict-title">Review the latest version before saving</h2>
            <p>
              The project is now at revision {project.revision}. Your unsaved entries are still in the
              form. The latest goal is: “{project.goal}”
            </p>
            <p>Latest requirements: {project.requirements.map((item) => item.label).join(" · ") || "None yet."}</p>
          </div>
          <div className="conflict-actions">
            <button
              className="button quiet-button"
              type="button"
              onClick={() => {
                setDraft(fromProject(project));
                setRequirementResetKey((current) => current + 1);
                setConflictNeedsReview(false);
                setSaveError("");
              }}
            >
              Use latest version
            </button>
            <button className="button secondary-button" type="button" onClick={() => setConflictNeedsReview(false)}>
              I reviewed this version
            </button>
          </div>
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
              {conflictNeedsReview && <span className="field-help">Review the latest version before continuing.</span>}
            </div>
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
            {project.requirements.map((requirement, index) => (
              <RequirementEditor
                key={`${requirement.id}-${requirementResetKey}`}
                project={project}
                requirement={requirement}
                index={index}
                blocked={conflictNeedsReview}
                onProjectUpdate={acceptProjectUpdate}
                onWriteError={reportWriteError}
              />
            ))}
          </ol>
          {project.requirements.length < 100 && (
            <NewRequirement
              project={project}
              blocked={conflictNeedsReview}
              onProjectUpdate={acceptProjectUpdate}
              onWriteError={reportWriteError}
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
        <button className="button danger-button" type="button" disabled={deleteProject.isPending || conflictNeedsReview} onClick={confirmDelete}>
          {deleteProject.isPending ? "Deleting…" : "Delete project"}
        </button>
      </section>
    </main>
  );
}

function FieldError({ id, message }: { id: string; message?: string }) {
  return message ? <p id={id} className="field-error">{message}</p> : null;
}

function RequirementEditor({
  project,
  requirement,
  index,
  blocked,
  onProjectUpdate,
  onWriteError,
}: {
  project: Project;
  requirement: Requirement;
  index: number;
  blocked: boolean;
  onProjectUpdate: (project: Project) => void;
  onWriteError: (error: unknown, fallback: string) => Promise<void>;
}) {
  const [draft, setDraft] = useState(() => fromRequirement(requirement));
  const [problem, setProblem] = useState("");
  const [saved, setSaved] = useState("");

  const patch = useMutation({
    mutationFn: (command: RequirementPatch) =>
      projectsApi.patchRequirement(project.id, requirement.id, command),
    onSuccess: (updated) => {
      onProjectUpdate(updated);
      const updatedRequirement = updated.requirements.find((item) => item.id === requirement.id);
      if (updatedRequirement) setDraft(fromRequirement(updatedRequirement));
      setProblem("");
      setSaved("Requirement saved.");
    },
    onError: (error) => {
      setSaved("");
      setProblem(readableError(error));
      return onWriteError(error, "Requirement could not be saved.");
    },
  });
  const remove = useMutation({
    mutationFn: (expectedVersion: number) =>
      projectsApi.deleteRequirement(project.id, requirement.id, expectedVersion),
    onSuccess: (updated) => onProjectUpdate(updated),
    onError: (error) => {
      setProblem(readableError(error));
      return onWriteError(error, "Requirement could not be removed.");
    },
  });

  function update<K extends keyof RequirementDraft>(field: K, value: RequirementDraft[K]) {
    setDraft((current) => ({ ...current, [field]: value }));
    setProblem("");
    setSaved("");
  }

  function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    let criterion: Partial<RequirementCreate>;
    try {
      criterion = requirementBody(draft);
    } catch (error) {
      setProblem(readableError(error));
      return;
    }
    const command: RequirementPatch = {
      expected_version: project.revision,
      kind: draft.kind,
      label: draft.label,
      detail: draft.detail.trim() || null,
      ...(draft.attributeKey.trim()
        ? criterion
        : { attribute_key: null }),
    };
    patch.mutate(command);
  }

  function move(position: number) {
    patch.mutate({ expected_version: project.revision, position });
  }

  function confirmRemove() {
    if (window.confirm(`Remove “${requirement.label}” from this project?`)) {
      remove.mutate(project.revision);
    }
  }

  const pending = patch.isPending || remove.isPending;
  const criterionId = `criterion-${requirement.id}`;

  return (
    <li className="requirement-item">
      <form onSubmit={save}>
        <div className="requirement-topline">
          <label className="sr-only" htmlFor={`kind-${requirement.id}`}>Requirement type</label>
          <select
            id={`kind-${requirement.id}`}
            value={draft.kind}
            onChange={(event) => update("kind", event.target.value as Requirement["kind"])}
          >
            {REQUIREMENT_KINDS.map((kind) => <option key={kind} value={kind}>{kind.replace("_", " ")}</option>)}
          </select>
          <span className="requirement-origin">Added by you</span>
        </div>
        <label className="sr-only" htmlFor={`label-${requirement.id}`}>Requirement</label>
        <input
          id={`label-${requirement.id}`}
          className="requirement-label-input"
          value={draft.label}
          maxLength={300}
          required
          onChange={(event) => update("label", event.target.value)}
        />
        <label className="sr-only" htmlFor={`detail-${requirement.id}`}>Requirement details</label>
        <textarea
          id={`detail-${requirement.id}`}
          value={draft.detail}
          rows={2}
          maxLength={2000}
          placeholder="Add a little more context (optional)"
          onChange={(event) => update("detail", event.target.value)}
        />
        <CriterionFields
          id={criterionId}
          draft={draft}
          onChange={update}
        />
        {problem && <p className="field-error" role="alert">{problem}</p>}
        {saved && <p className="save-message" role="status">{saved}</p>}
        <div className="requirement-actions">
          <button className="button small-button primary-button" type="submit" disabled={pending || blocked}>
            {patch.isPending ? "Saving…" : "Save requirement"}
          </button>
          <button
            className="button small-button quiet-button"
            type="button"
            aria-label={`Move ${requirement.label} up`}
            disabled={pending || blocked || index === 0}
            onClick={() => move(index - 1)}
          >
            Move up
          </button>
          <button
            className="button small-button quiet-button"
            type="button"
            aria-label={`Move ${requirement.label} down`}
            disabled={pending || blocked || index === project.requirements.length - 1}
            onClick={() => move(index + 1)}
          >
            Move down
          </button>
          <button
            className="button small-button text-danger-button"
            type="button"
            disabled={pending || blocked}
            onClick={confirmRemove}
          >
            {remove.isPending ? "Removing…" : "Remove"}
          </button>
        </div>
      </form>
    </li>
  );
}

function CriterionFields({
  id,
  draft,
  onChange,
}: {
  id: string;
  draft: RequirementDraft;
  onChange: <K extends keyof RequirementDraft>(field: K, value: RequirementDraft[K]) => void;
}) {
  return (
    <fieldset className="criterion-fields">
      <legend>Structured criterion <span className="optional">Optional</span></legend>
      <label className="field-label" htmlFor={`${id}-attribute`}>Attribute key</label>
      <input
        id={`${id}-attribute`}
        value={draft.attributeKey}
        maxLength={100}
        placeholder="Example: weight_kg"
        onChange={(event) => onChange("attributeKey", event.target.value)}
      />
      {draft.attributeKey.trim() && (
        <div className="field-grid criterion-grid">
          <div>
            <label className="field-label" htmlFor={`${id}-operator`}>Operator</label>
            <select
              id={`${id}-operator`}
              value={draft.operator}
              onChange={(event) => onChange("operator", event.target.value as RequirementDraft["operator"])}
            >
              <option value="">Choose operator</option>
              {REQUIREMENT_OPERATORS.map((operator) => <option key={operator} value={operator}>{operator}</option>)}
            </select>
          </div>
          <div>
            <label className="field-label" htmlFor={`${id}-unit`}>Unit <span className="optional">Optional</span></label>
            <input
              id={`${id}-unit`}
              value={draft.unit}
              maxLength={50}
              placeholder="kg, inches…"
              onChange={(event) => onChange("unit", event.target.value)}
            />
          </div>
          <div className="field-span-two">
            <label className="field-label" htmlFor={`${id}-value`}>Value as JSON</label>
            <input
              id={`${id}-value`}
              value={draft.value}
              placeholder={'true, 4, "lightweight", or ["one", "two"]'}
              onChange={(event) => onChange("value", event.target.value)}
            />
            <p className="field-help">Text values need double quotes. Leave this section blank for a text-only requirement.</p>
          </div>
        </div>
      )}
    </fieldset>
  );
}

function NewRequirement({
  project,
  blocked,
  onProjectUpdate,
  onWriteError,
}: {
  project: Project;
  blocked: boolean;
  onProjectUpdate: (project: Project) => void;
  onWriteError: (error: unknown, fallback: string) => Promise<void>;
}) {
  const [draft, setDraft] = useState<RequirementDraft>({
    kind: "must_have",
    label: "",
    detail: "",
    attributeKey: "",
    operator: "",
    value: "",
    unit: "",
  });
  const [problem, setProblem] = useState("");
  const queryClient = useQueryClient();
  const create = useMutation({
    mutationFn: ({ expectedVersion, command }: { expectedVersion: number; command: RequirementCreate }) =>
      projectsApi.createRequirement(project.id, expectedVersion, command),
    onSuccess: (updated) => {
      queryClient.setQueryData(["project", project.id], updated);
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
      onProjectUpdate(updated);
      setDraft({ kind: "must_have", label: "", detail: "", attributeKey: "", operator: "", value: "", unit: "" });
      setProblem("");
    },
    onError: (error) => {
      setProblem(readableError(error));
      return onWriteError(error, "Requirement could not be added.");
    },
  });

  function update<K extends keyof RequirementDraft>(field: K, value: RequirementDraft[K]) {
    setDraft((current) => ({ ...current, [field]: value }));
    setProblem("");
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    let criterion: Partial<RequirementCreate>;
    try {
      criterion = requirementBody(draft);
    } catch (error) {
      setProblem(readableError(error));
      return;
    }
    create.mutate({
      expectedVersion: project.revision,
      command: {
        kind: draft.kind,
        label: draft.label,
        detail: draft.detail.trim() || null,
        ...criterion,
      },
    });
  }

  return (
    <form className="new-requirement" onSubmit={submit}>
      <div className="section-heading add-heading">
        <span className="add-mark" aria-hidden="true">+</span>
        <div>
          <p className="eyebrow">Make it specific</p>
          <h3>Add a requirement</h3>
        </div>
      </div>
      <div className="field-grid">
        <div>
          <label className="field-label" htmlFor="new-requirement-kind">Type</label>
          <select
            id="new-requirement-kind"
            value={draft.kind}
            onChange={(event) => update("kind", event.target.value as Requirement["kind"])}
          >
            {REQUIREMENT_KINDS.map((kind) => <option key={kind} value={kind}>{kind.replace("_", " ")}</option>)}
          </select>
        </div>
        <div className="field-span-two">
          <label className="field-label" htmlFor="new-requirement-label">Requirement</label>
          <input
            id="new-requirement-label"
            value={draft.label}
            onChange={(event) => update("label", event.target.value)}
            maxLength={300}
            required
            placeholder="Works well on pet hair"
          />
        </div>
        <div className="field-span-two">
          <label className="field-label" htmlFor="new-requirement-detail">Details <span className="optional">Optional</span></label>
          <textarea
            id="new-requirement-detail"
            value={draft.detail}
            onChange={(event) => update("detail", event.target.value)}
            maxLength={2000}
            rows={2}
          />
        </div>
      </div>
      <CriterionFields id="new-criterion" draft={draft} onChange={update} />
      {problem && <p className="field-error" role="alert">{problem}</p>}
      <button className="button secondary-button" type="submit" disabled={create.isPending || blocked}>
        {create.isPending ? "Adding…" : "Add requirement"}
      </button>
    </form>
  );
}
