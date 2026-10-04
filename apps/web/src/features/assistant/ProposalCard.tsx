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
          </ul>
          <div className="assistant-proposal-actions">
            <button className="button secondary-button small-button" type="button" disabled={pending || blocked} onClick={onApply}>
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
