import { Project, ProposalRead } from "../../api/client";

export function ProposalCard({
  proposal,
  project,
  pending,
  blocked,
  onApply,
  onDismiss,
}: {
  proposal: ProposalRead;
  project: Project;
  pending: boolean;
  blocked: boolean;
  onApply: () => void;
  onDismiss: () => void;
}) {
  const operations = proposal.operations;
  const projectUpdates = isRecord(operations.project_updates) ? operations.project_updates : {};
  const requirementOperations = Array.isArray(operations.requirement_operations)
    ? operations.requirement_operations.filter(isRecord)
    : [];
  const decisionOperations = Array.isArray(operations.decision_operations)
    ? operations.decision_operations.filter(isRecord)
    : [];
  const canPreview = canPreviewProposal(operations, projectUpdates, requirementOperations, decisionOperations);
  const isStale =
    proposal.status === "stale" ||
    (proposal.status === "pending" && proposal.base_revision !== project.revision);
  const displayStatus = isStale ? "stale" : proposal.status;

  return (
    <section className="assistant-proposal" aria-label="AI suggestion">
      <div className="assistant-proposal-heading">
        <strong>AI suggestion</strong>
        <span className={`assistant-proposal-status assistant-proposal-${displayStatus}`}>{displayStatus}</span>
      </div>
      {displayStatus === "pending" ? (
        <>
          <p className="assistant-proposal-base">Based on project revision {proposal.base_revision}</p>
          <ul className="assistant-diff-list">
            {Object.entries(projectUpdates).map(([key, value]) => (
              <li key={key}>
                <span>{humanize(key)}</span>
                <strong>{displayValue(projectField(project, key))} → {displayValue(value)}</strong>
              </li>
            ))}
            {requirementOperations.map((item, index) => {
              const fields = isRecord(item.fields) ? item.fields : {};
              const current = project.requirements.find((requirement) => requirement.id === item.id);
              const operation = item.operation;
              if (operation === "add") {
                return (
                  <li key={`add-${index}`}>
                    <span>Add {String(fields.kind ?? "requirement")}</span>
                    <strong>{String(fields.label ?? "New requirement")}</strong>
                    {typeof fields.detail === "string" && <small>{fields.detail}</small>}
                    {criterionSummary(fields) && <small>{criterionSummary(fields)}</small>}
                  </li>
                );
              }
              if (operation === "remove") {
                return (
                  <li key={`remove-${String(item.id)}-${index}`}>
                    <span>Remove {current?.kind ?? "requirement"}</span>
                    <strong>{current?.label ?? `Requirement ${String(item.id ?? "")}`}</strong>
                  </li>
                );
              }
              return (
                <li key={`update-${String(item.id)}-${index}`}>
                  <span>Update {current?.kind ?? "requirement"}</span>
                  <strong>{current?.label ?? `Requirement ${String(item.id ?? "")}`}</strong>
                  {Object.entries(fields).map(([key, value]) => (
                    <small key={key}>
                      {humanize(key)}: {displayValue(current?.[key as keyof typeof current])} → {displayValue(value)}
                    </small>
                  ))}
                </li>
              );
            })}
            {decisionOperations.map((item, index) => renderDecisionOperation(item, index))}
          </ul>
          {!canPreview && <p className="field-error" role="alert">This suggestion contains an operation that cannot be previewed safely, so it cannot be applied.</p>}
          <div className="assistant-proposal-actions">
            <button className="button secondary-button small-button" type="button" disabled={pending || blocked || !canPreview} onClick={onApply}>
              {pending ? "Saving…" : "Apply suggestion"}
            </button>
            <button className="button quiet-button small-button" type="button" disabled={pending} onClick={onDismiss}>
              Dismiss
            </button>
          </div>
        </>
      ) : proposal.status === "applied" ? (
        <p className="assistant-proposal-base">Applied at project revision {proposal.applied_revision}.</p>
      ) : displayStatus === "stale" ? (
        <>
          <p className="assistant-proposal-base">The project changed after this suggestion was prepared. Ask for a fresh suggestion.</p>
          {proposal.status === "pending" && (
            <div className="assistant-proposal-actions">
              <button className="button quiet-button small-button" type="button" disabled={pending} onClick={onDismiss}>
                {pending ? "Saving…" : "Dismiss suggestion"}
              </button>
            </div>
          )}
        </>
      ) : (
        <p className="assistant-proposal-base">Dismissed. The project was not changed.</p>
      )}
    </section>
  );
}

function projectField(project: Project, field: string): unknown {
  if (field === "budget_target" || field === "budget_maximum") return project[field];
  if (field === "goal" || field === "category" || field === "budget_currency") return project[field];
  return undefined;
}

function criterionSummary(fields: Record<string, unknown>): string {
  if (!("attribute_key" in fields) || !("operator" in fields) || !("value" in fields)) return "";
  return `${String(fields.attribute_key)} ${String(fields.operator)} ${displayValue(fields.value)}${fields.unit ? ` ${String(fields.unit)}` : ""}`;
}

function humanize(value: string) {
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function displayValue(value: unknown): string {
  if (value === null || value === undefined) return "Unknown";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function canPreviewProposal(
  operations: Record<string, unknown>,
  projectUpdates: Record<string, unknown>,
  requirementOperations: Record<string, unknown>[],
  decisionOperations: Record<string, unknown>[],
) {
  const projectFields = new Set(["goal", "category", "budget_target", "budget_maximum", "budget_currency"]);
  const requirementKinds = new Set(["add", "update", "remove"]);
  const decisionKinds = new Set(["shortlist", "reject", "add_note", "set_comparison_dimensions"]);
  const rawRequirementOperations = operations.requirement_operations;
  const rawDecisionOperations = operations.decision_operations;
  if (!isRecord(operations.project_updates) || !Array.isArray(rawRequirementOperations) || (rawDecisionOperations !== undefined && !Array.isArray(rawDecisionOperations))) return false;
  if (Object.keys(projectUpdates).some((key) => !projectFields.has(key))) return false;
  if (Object.values(projectUpdates).some((value) => typeof value !== "string")) return false;
  const rawDecisions = Array.isArray(rawDecisionOperations) ? rawDecisionOperations : [];
  if (requirementOperations.length !== rawRequirementOperations.length || decisionOperations.length !== rawDecisions.length) return false;
  if (requirementOperations.some((item) => {
    if (!requirementKinds.has(String(item.operation))) return true;
    if (item.operation === "add") return !isRecord(item.fields) || !hasPreviewableRequirementFields(item.fields, true);
    if (!isUuid(item.id)) return true;
    if (item.operation === "remove") return Object.keys(item).some((key) => !["operation", "id"].includes(key));
    return !isRecord(item.fields) || !hasPreviewableRequirementFields(item.fields, false);
  })) return false;
  if (Object.keys(projectUpdates).length === 0 && requirementOperations.length === 0 && decisionOperations.length === 0) return false;
  return decisionOperations.every((item) => {
    if (!decisionKinds.has(String(item.operation))) return false;
    if (item.operation === "shortlist") return isUuid(item.project_product_id) && isOnlyKeys(item, ["operation", "project_product_id", "reason", "concerns"]) && isOptionalString(item.reason) && isOptionalStringArray(item.concerns);
    if (item.operation === "reject") return isUuid(item.project_product_id) && isOnlyKeys(item, ["operation", "project_product_id", "reason", "concerns", "rejection_reason"]) && isOptionalString(item.reason) && isOptionalStringArray(item.concerns) && ["too_expensive", "missing_feature", "too_large", "appearance", "weak_evidence", "wrong_category", "already_owned", "other"].includes(String(item.rejection_reason));
    if (item.operation === "add_note") return typeof item.text === "string" && item.text.trim().length > 0 && (item.project_product_id === undefined || item.project_product_id === null || isUuid(item.project_product_id)) && isOnlyKeys(item, ["operation", "text", "project_product_id"]);
    if (item.operation === "set_comparison_dimensions") {
      return Array.isArray(item.project_product_ids) && item.project_product_ids.length >= 2 && item.project_product_ids.length <= 6 &&
        item.project_product_ids.every(isUuid) && new Set(item.project_product_ids).size === item.project_product_ids.length && Array.isArray(item.dimensions) &&
        item.dimensions.length >= 1 && item.dimensions.length <= 20 && item.dimensions.every(isPreviewableDimension) &&
        new Set(item.dimensions.map((dimension) => (dimension as Record<string, unknown>).key)).size === item.dimensions.length &&
        typeof item.title === "string" && item.title.trim().length > 0 && (item.display_mode === "all" || item.display_mode === "differences") &&
        ((item.comparison_id === undefined || item.comparison_id === null) === (item.expected_comparison_version === undefined || item.expected_comparison_version === null)) &&
        (item.comparison_id === undefined || item.comparison_id === null || (isUuid(item.comparison_id) && Number.isInteger(item.expected_comparison_version) && Number(item.expected_comparison_version) > 0)) &&
        isOnlyKeys(item, ["operation", "project_product_ids", "dimensions", "title", "display_mode", "comparison_id", "expected_comparison_version"]);
    }
    return false;
  });
}

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

function isUuid(value: unknown): value is string {
  return typeof value === "string" && UUID_PATTERN.test(value);
}

function isOnlyKeys(value: Record<string, unknown>, allowed: string[]) {
  return Object.keys(value).every((key) => allowed.includes(key));
}

function isOptionalString(value: unknown) {
  return value === undefined || typeof value === "string";
}

function isOptionalStringArray(value: unknown) {
  return value === undefined || (Array.isArray(value) && value.length <= 20 && value.every((item) => typeof item === "string"));
}

function hasPreviewableRequirementFields(fields: Record<string, unknown>, isNew: boolean) {
  const allowed = ["kind", "label", "detail", "attribute_key", "operator", "value", "unit"];
  if (!Object.keys(fields).length || !isOnlyKeys(fields, allowed)) return false;
  if ("kind" in fields && typeof fields.kind !== "string") return false;
  if ("label" in fields && typeof fields.label !== "string") return false;
  if ("detail" in fields && fields.detail !== null && typeof fields.detail !== "string") return false;
  if ("attribute_key" in fields && fields.attribute_key !== null && typeof fields.attribute_key !== "string") return false;
  if ("operator" in fields && fields.operator !== null && typeof fields.operator !== "string") return false;
  if ("unit" in fields && fields.unit !== null && typeof fields.unit !== "string") return false;
  return !isNew || (typeof fields.kind === "string" && typeof fields.label === "string");
}

function isPreviewableDimension(value: unknown) {
  if (!isRecord(value) || !isOnlyKeys(value, ["key", "label", "unit", "dimension_type"])) return false;
  return typeof value.key === "string" && value.key.length > 0 &&
    typeof value.label === "string" && value.label.length > 0 &&
    (value.unit === undefined || value.unit === null || typeof value.unit === "string") &&
    ["fact", "offer", "evidence", "project_fit", "user_note"].includes(String(value.dimension_type));
}

function renderDecisionOperation(item: Record<string, unknown>, index: number) {
  const operation = item.operation;
  const target = typeof item.project_product_id === "string" ? item.project_product_id : "";
  if (operation === "shortlist" || operation === "reject") {
    return (
      <li key={`decision-${index}`}>
        <span>{operation === "shortlist" ? "Shortlist variant" : `Reject variant · ${humanize(String(item.rejection_reason ?? "other"))}`}</span>
        <strong>Project variant {target}</strong>
        {typeof item.reason === "string" && item.reason && <small>Reason: {item.reason}</small>}
        {Array.isArray(item.concerns) && item.concerns.length > 0 && <small>Concerns: {item.concerns.map(String).join(" · ")}</small>}
      </li>
    );
  }
  if (operation === "add_note") {
    return (
      <li key={`note-${index}`}>
        <span>Append to {target ? `variant ${target}` : "project"} note</span>
        <strong>{String(item.text ?? "")}</strong>
        <small>Existing note text is preserved; this text is added after it.</small>
      </li>
    );
  }
  if (operation === "set_comparison_dimensions") {
    const ids = Array.isArray(item.project_product_ids) ? item.project_product_ids.map(String) : [];
    const dimensions = Array.isArray(item.dimensions) ? item.dimensions.filter(isRecord) : [];
    return (
      <li key={`comparison-${index}`}>
        <span>{item.comparison_id ? "Update comparison" : "Create comparison"}</span>
        <strong>{String(item.title ?? "Untitled comparison")}</strong>
        {item.comparison_id !== undefined && item.comparison_id !== null && <small>Saved comparison {String(item.comparison_id)} · revision {String(item.expected_comparison_version)}</small>}
        <small>Variants: {ids.join(" · ")}</small>
        <small>Dimensions: {dimensions.map((dimension) => `${String(dimension.label)} (${String(dimension.dimension_type)}: ${String(dimension.key)})`).join(" · ")}</small>
        <small>Display: {String(item.display_mode ?? "all")}</small>
      </li>
    );
  }
  return <li key={`unsupported-${index}`}>Unsupported assistant operation</li>;
}
