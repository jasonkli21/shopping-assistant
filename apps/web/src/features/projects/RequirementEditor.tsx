import { useMutation, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useEffect, useRef, useState } from "react";

import { Project, Requirement, RequirementCreate, RequirementPatch, projectsApi } from "../../api/client";
import {
  displayRequirementValue,
  fromRequirement,
  reconcileRequirementDraft,
  readableError,
  requirementBody,
  requirementDraftIsDirty,
  requirementPatch,
  sameRequirementDraft,
  REQUIREMENT_FIELDS,
  REQUIREMENT_FIELD_LABELS,
  REQUIREMENT_KINDS,
  REQUIREMENT_OPERATORS,
  type ConflictChoice,
  type RequirementDraft,
  type RequirementField,
} from "./projectDrafts";
export function FieldError({ id, message }: { id: string; message?: string }) {
  return message ? <p id={id} className="field-error">{message}</p> : null;
}

export function RequirementEditor({
  project,
  requirement,
  latestRequirement,
  index,
  blocked,
  onProjectUpdate,
  onWriteError,
  onForget,
  onDraftStateChange,
}: {
  project: Project;
  requirement: Requirement;
  latestRequirement?: Requirement;
  index: number;
  blocked: boolean;
  onProjectUpdate: (project: Project) => void;
  onWriteError: (error: unknown, fallback: string, attemptedProject?: Project) => Promise<Project | null>;
  onForget: () => void;
  onDraftStateChange: (key: string, dirty: boolean) => void;
}) {
  const [draft, setDraft] = useState(() => fromRequirement(requirement));
  const [base, setBase] = useState(requirement);
  const [problem, setProblem] = useState("");
  const [saved, setSaved] = useState("");
  const [conflict, setConflict] = useState<{ base: Requirement; latest: Requirement | null } | null>(null);
  const [conflictChoices, setConflictChoices] = useState<Partial<Record<RequirementField, ConflictChoice>>>({});
  const hasForgotten = useRef(false);

  const patch = useMutation({
    mutationFn: ({ command }: { command: RequirementPatch; attemptedProject: Project }) =>
      projectsApi.patchRequirement(project.id, requirement.id, command),
    onSuccess: (updated) => {
      onProjectUpdate(updated);
      const updatedRequirement = updated.requirements.find((item) => item.id === requirement.id);
      if (updatedRequirement) {
        setBase(updatedRequirement);
        setDraft(fromRequirement(updatedRequirement));
      }
      setConflict(null);
      setConflictChoices({});
      setProblem("");
      setSaved("Requirement saved.");
    },
    onError: async (error, variables) => {
      setSaved("");
      setProblem(readableError(error));
      await onWriteError(error, "Requirement could not be saved.", variables.attemptedProject);
    },
  });
  const remove = useMutation({
    mutationFn: ({ expectedVersion }: { expectedVersion: number; attemptedProject: Project }) =>
      projectsApi.deleteRequirement(project.id, requirement.id, expectedVersion),
    onSuccess: (updated) => onProjectUpdate(updated),
    onError: async (error, variables) => {
      setProblem(readableError(error));
      await onWriteError(error, "Requirement could not be removed.", variables.attemptedProject);
    },
  });

  const dirty = requirementDraftIsDirty(draft, fromRequirement(base));
  const pending = patch.isPending || remove.isPending;

  useEffect(() => {
    onDraftStateChange(requirement.id, dirty || pending);
    return () => onDraftStateChange(requirement.id, false);
  }, [dirty, onDraftStateChange, pending, requirement.id]);

  useEffect(() => {
    if (patch.isPending || remove.isPending) return;
    const mergeBase = conflict?.base ?? base;
    if (!latestRequirement) {
      if (requirementDraftIsDirty(draft, fromRequirement(mergeBase))) {
        hasForgotten.current = false;
        if (!conflict || conflict.latest !== null) {
          setConflict({ base: mergeBase, latest: null });
          setConflictChoices({});
        }
      } else if (!hasForgotten.current) {
        hasForgotten.current = true;
        onForget();
      }
      return;
    }

    hasForgotten.current = false;
    const latestDraft = fromRequirement(latestRequirement);
    const merged = reconcileRequirementDraft(fromRequirement(mergeBase), draft, latestDraft);
    if (merged.conflicts.length) {
      if (conflict?.latest?.id !== latestRequirement.id || conflict.latest.updated_at !== latestRequirement.updated_at) {
        setConflict({ base: mergeBase, latest: latestRequirement });
        setConflictChoices({});
      }
      return;
    }

    setBase(latestRequirement);
    if (!sameRequirementDraft(draft, merged.draft)) setDraft(merged.draft);
    if (conflict) {
      setConflict(null);
      setConflictChoices({});
    }
  }, [base, conflict, draft, latestRequirement, onForget, patch.isPending, project.revision, remove.isPending]);

  function update<K extends keyof RequirementDraft>(field: K, value: RequirementDraft[K]) {
    setDraft((current) => ({ ...current, [field]: value }));
    setConflictChoices((current) => {
      const next = { ...current };
      delete next[field];
      return next;
    });
    setProblem("");
    setSaved("");
  }

  function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (patch.isPending || remove.isPending || !latestRequirement || conflict || blocked || !dirty) return;
    try {
      requirementBody(draft);
    } catch (error) {
      setProblem(readableError(error));
      return;
    }
    const command = requirementPatch(draft, fromRequirement(base), project.revision);
    patch.mutate({ command, attemptedProject: project });
  }

  function move(position: number) {
    if (patch.isPending || remove.isPending || !latestRequirement || dirty || conflict || blocked) return;
    patch.mutate({ command: { expected_version: project.revision, position }, attemptedProject: project });
  }

  function confirmRemove() {
    if (patch.isPending || remove.isPending || !latestRequirement || dirty || conflict || blocked) return;
    if (window.confirm(`Remove “${requirement.label}” from this project?`)) {
      remove.mutate({ expectedVersion: project.revision, attemptedProject: project });
    }
  }

  function finishRequirementReconciliation() {
    if (!conflict?.latest) return;
    const resolved = reconcileRequirementDraft(
      fromRequirement(conflict.base),
      draft,
      fromRequirement(conflict.latest),
      conflictChoices,
    );
    if (resolved.conflicts.length) return;
    setBase(conflict.latest);
    setDraft(resolved.draft);
    setConflict(null);
    setConflictChoices({});
    setProblem("");
  }

  const criterionId = `criterion-${requirement.id}`;

  if (!latestRequirement && !dirty && !conflict) return null;

  return (
    <li className="requirement-item">
      {conflict && (
        <div className="notice conflict-notice requirement-conflict" role="alert">
          {conflict.latest ? (
            <>
              <p><strong>This requirement changed in another edit.</strong> Compare the saved values with your draft.</p>
              <ul className="conflict-differences">
                {REQUIREMENT_FIELDS.filter((field) => {
                  const original = fromRequirement(conflict.base)[field];
                  const latest = fromRequirement(conflict.latest!)[field];
                  return original !== latest || original !== draft[field];
                }).map((field) => {
                  const original = fromRequirement(conflict.base)[field];
                  const latest = fromRequirement(conflict.latest!)[field];
                  const overlaps = original !== draft[field] && original !== latest && draft[field] !== latest;
                  return (
                    <li key={field}>
                      <strong>{REQUIREMENT_FIELD_LABELS[field]}</strong>
                      <span>Latest saved: {displayRequirementValue(latest)}</span>
                      <span>Your draft: {displayRequirementValue(draft[field])}</span>
                      {overlaps && (
                        <div className="conflict-field-actions" aria-label={`Choose ${REQUIREMENT_FIELD_LABELS[field]}`}>
                          <button
                            className="button small-button quiet-button"
                            type="button"
                            aria-pressed={conflictChoices[field] === "mine"}
                            onClick={() => setConflictChoices((current) => ({ ...current, [field]: "mine" }))}
                          >Keep my {REQUIREMENT_FIELD_LABELS[field].toLowerCase()}</button>
                          <button
                            className="button small-button quiet-button"
                            type="button"
                            aria-pressed={conflictChoices[field] === "latest"}
                            onClick={() => setConflictChoices((current) => ({ ...current, [field]: "latest" }))}
                          >Use latest {REQUIREMENT_FIELD_LABELS[field].toLowerCase()}</button>
                        </div>
                      )}
                    </li>
                  );
                })}
              </ul>
              <button
                className="button small-button secondary-button"
                type="button"
                disabled={Boolean(reconcileRequirementDraft(
                  fromRequirement(conflict.base), draft, fromRequirement(conflict.latest), conflictChoices,
                ).conflicts.length)}
                onClick={finishRequirementReconciliation}
              >Apply requirement draft</button>
            </>
          ) : (
            <>
              <p><strong>This requirement was removed in the latest version.</strong> Your draft is preserved below.</p>
              <button className="button small-button quiet-button" type="button" onClick={onForget}>Discard this draft</button>
            </>
          )}
        </div>
      )}
      <form onSubmit={save}>
        <fieldset className="pending-fieldset" disabled={pending || blocked}>
          <legend className="sr-only">Edit requirement</legend>
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
          <button className="button small-button primary-button" type="submit" disabled={pending || blocked || Boolean(conflict) || !latestRequirement || !dirty}>
            {patch.isPending ? "Saving…" : "Save requirement"}
          </button>
          <button
            className="button small-button quiet-button"
            type="button"
            aria-label={`Move ${requirement.label} up`}
            disabled={pending || blocked || Boolean(conflict) || dirty || !latestRequirement || index === 0}
            onClick={() => move(index - 1)}
          >
            Move up
          </button>
          <button
            className="button small-button quiet-button"
            type="button"
            aria-label={`Move ${requirement.label} down`}
            disabled={pending || blocked || Boolean(conflict) || dirty || !latestRequirement || index === project.requirements.length - 1}
            onClick={() => move(index + 1)}
          >
            Move down
          </button>
          <button
            className="button small-button text-danger-button"
            type="button"
            disabled={pending || blocked || Boolean(conflict) || dirty || !latestRequirement}
            onClick={confirmRemove}
          >
            {remove.isPending ? "Removing…" : "Remove"}
          </button>
        </div>
        </fieldset>
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

export function NewRequirement({
  project,
  blocked,
  onProjectUpdate,
  onWriteError,
  onDraftStateChange,
}: {
  project: Project;
  blocked: boolean;
  onProjectUpdate: (project: Project) => void;
  onWriteError: (error: unknown, fallback: string, attemptedProject?: Project) => Promise<Project | null>;
  onDraftStateChange: (key: string, dirty: boolean) => void;
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
    mutationFn: ({ expectedVersion, command }: { expectedVersion: number; command: RequirementCreate; attemptedProject: Project }) =>
      projectsApi.createRequirement(project.id, expectedVersion, command),
    onSuccess: (updated) => {
      queryClient.setQueryData(["project", project.id], updated);
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
      onProjectUpdate(updated);
      setDraft({ kind: "must_have", label: "", detail: "", attributeKey: "", operator: "", value: "", unit: "" });
      setProblem("");
    },
    onError: async (error, variables) => {
      setProblem(readableError(error));
      await onWriteError(error, "Requirement could not be added.", variables.attemptedProject);
    },
  });

  const emptyDraft: RequirementDraft = {
    kind: "must_have",
    label: "",
    detail: "",
    attributeKey: "",
    operator: "",
    value: "",
    unit: "",
  };
  const dirty = requirementDraftIsDirty(draft, emptyDraft);
  useEffect(() => {
    onDraftStateChange("new-requirement", dirty || create.isPending);
    return () => onDraftStateChange("new-requirement", false);
  }, [create.isPending, dirty, onDraftStateChange]);

  function update<K extends keyof RequirementDraft>(field: K, value: RequirementDraft[K]) {
    setDraft((current) => ({ ...current, [field]: value }));
    setProblem("");
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (create.isPending || blocked) return;
    let criterion: Partial<RequirementCreate>;
    try {
      criterion = requirementBody(draft);
    } catch (error) {
      setProblem(readableError(error));
      return;
    }
    create.mutate({
      expectedVersion: project.revision,
      attemptedProject: project,
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
      <fieldset className="pending-fieldset" disabled={create.isPending || blocked}>
        <legend className="sr-only">New requirement</legend>
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
      </fieldset>
    </form>
  );
}
