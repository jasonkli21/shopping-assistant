import { ApiRequestError, Project, ProjectPatch, Requirement, RequirementCreate, RequirementPatch } from "../../api/client";

export type ProjectDraft = {
  title: string;
  goal: string;
  category: string;
  status: Project["status"];
  budgetTarget: string;
  budgetMaximum: string;
  budgetCurrency: string;
  notes: string;
};

export type RequirementDraft = {
  kind: Requirement["kind"];
  label: string;
  detail: string;
  attributeKey: string;
  operator: NonNullable<Requirement["operator"]> | "";
  value: string;
  unit: string;
};

export const CURRENCIES = ["USD", "CAD", "EUR", "GBP", "JPY", "AUD", "NZD", "CHF", "CNY", "INR"];
export const REQUIREMENT_KINDS: Requirement["kind"][] = ["must_have", "preference", "constraint"];
export const REQUIREMENT_OPERATORS: NonNullable<Requirement["operator"]>[] = [
  "eq",
  "gte",
  "lte",
  "contains",
  "one_of",
];

export function fromProject(project: Project): ProjectDraft {
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

export function fromRequirement(requirement: Requirement): RequirementDraft {
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

export type RequirementField = keyof RequirementDraft;
export const REQUIREMENT_FIELDS: RequirementField[] = [
  "kind", "label", "detail", "attributeKey", "operator", "value", "unit",
];
export const REQUIREMENT_FIELD_LABELS: Record<RequirementField, string> = {
  kind: "Type",
  label: "Requirement",
  detail: "Details",
  attributeKey: "Attribute key",
  operator: "Operator",
  value: "Value",
  unit: "Unit",
};

export type ConflictChoice = "mine" | "latest";

function reconcileFields<T extends Record<keyof T, string>, Field extends keyof T>(
  base: T,
  local: T,
  latest: T,
  fields: readonly Field[],
  choices: Partial<Record<Field, ConflictChoice>> = {},
): { draft: T; conflicts: Field[] } {
  const merged = { ...latest };
  const conflicts: Field[] = [];
  for (const field of fields) {
    const localChanged = local[field] !== base[field];
    const latestChanged = latest[field] !== base[field];
    if (!localChanged) continue;
    if (!latestChanged || local[field] === latest[field]) {
      merged[field] = local[field] as T[Field];
      continue;
    }
    const choice = choices[field];
    if (choice === "mine") merged[field] = local[field] as T[Field];
    else if (choice === "latest") merged[field] = latest[field] as T[Field];
    else {
      merged[field] = local[field] as T[Field];
      conflicts.push(field);
    }
  }
  return { draft: merged, conflicts };
}

export function reconcileRequirementDraft(
  base: RequirementDraft,
  local: RequirementDraft,
  latest: RequirementDraft,
  choices: Partial<Record<RequirementField, ConflictChoice>> = {},
): { draft: RequirementDraft; conflicts: RequirementField[] } {
  return reconcileFields(base, local, latest, REQUIREMENT_FIELDS, choices);
}

export function requirementPatch(draft: RequirementDraft, current: RequirementDraft, expectedVersion: number): RequirementPatch {
  const command: RequirementPatch = { expected_version: expectedVersion };
  if (draft.kind !== current.kind) command.kind = draft.kind;
  if (draft.label !== current.label) command.label = draft.label;
  const detail = draft.detail.trim() || null;
  if (detail !== (current.detail.trim() || null)) command.detail = detail;

  const structureChanged = draft.attributeKey !== current.attributeKey || draft.operator !== current.operator ||
    draft.value !== current.value || draft.unit !== current.unit;
  if (structureChanged) {
    const criterion = requirementBody(draft);
    if (draft.attributeKey.trim()) {
      command.attribute_key = criterion.attribute_key;
      command.operator = criterion.operator;
      command.value = criterion.value;
      command.unit = criterion.unit;
    } else {
      command.attribute_key = null;
      command.operator = null;
      command.value = null;
      command.unit = null;
    }
  }
  return command;
}

export function requirementDraftIsDirty(draft: RequirementDraft, current: RequirementDraft): boolean {
  return REQUIREMENT_FIELDS.some((field) => {
    if (field === "detail") return (draft.detail.trim() || "") !== (current.detail.trim() || "");
    return draft[field] !== current[field];
  });
}

export function sameRequirementDraft(left: RequirementDraft, right: RequirementDraft): boolean {
  return REQUIREMENT_FIELDS.every((field) => left[field] === right[field]);
}

export function displayRequirementValue(value: string): string {
  return value.trim() || "(empty)";
}

export function fieldErrors(error: unknown): Record<string, string> {
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

export function readableError(error: unknown): string {
  return error instanceof Error ? error.message : "The request could not be completed.";
}

export function projectValues(draft: ProjectDraft): Omit<ProjectPatch, "expected_version"> {
  const hasBudget = Boolean(draft.budgetTarget.trim() || draft.budgetMaximum.trim());
  return {
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

export type ProjectField = keyof ProjectDraft;
export const PROJECT_FIELDS: ProjectField[] = [
  "title", "goal", "category", "status", "budgetTarget", "budgetMaximum", "budgetCurrency", "notes",
];
export const PROJECT_FIELD_LABELS: Record<ProjectField, string> = {
  title: "Project name",
  goal: "Goal",
  category: "Category",
  status: "Project status",
  budgetTarget: "Budget target",
  budgetMaximum: "Budget maximum",
  budgetCurrency: "Budget currency",
  notes: "Notes",
};

export function projectPatch(draft: ProjectDraft, current: ProjectDraft, expectedVersion: number): ProjectPatch {
  const desired = projectValues(draft);
  const existing = projectValues(current);
  const patch: ProjectPatch = { expected_version: expectedVersion };
  if (desired.title !== existing.title) patch.title = desired.title;
  if (desired.goal !== existing.goal) patch.goal = desired.goal;
  if (desired.category !== existing.category) patch.category = desired.category;
  if (desired.status !== existing.status) patch.status = desired.status;
  if (desired.budget_target !== existing.budget_target) patch.budget_target = desired.budget_target;
  if (desired.budget_maximum !== existing.budget_maximum) patch.budget_maximum = desired.budget_maximum;
  if (desired.budget_currency !== existing.budget_currency) patch.budget_currency = desired.budget_currency;
  if (desired.notes !== existing.notes) patch.notes = desired.notes;
  return patch;
}

export function reconcileProjectDraft(
  base: ProjectDraft,
  local: ProjectDraft,
  latest: ProjectDraft,
  choices: Partial<Record<ProjectField, ConflictChoice>> = {},
): { draft: ProjectDraft; conflicts: ProjectField[] } {
  return reconcileFields(base, local, latest, PROJECT_FIELDS, choices);
}

export function displayProjectValue(value: string): string {
  return value.trim() || "(empty)";
}

export function requirementBody(draft: RequirementDraft): Omit<RequirementCreate, "kind" | "label" | "detail"> {
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
