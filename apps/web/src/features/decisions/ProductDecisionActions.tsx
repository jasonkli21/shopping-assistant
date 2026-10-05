import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  ApiRequestError,
  DecisionCommand,
  Project,
  decisionsApi,
} from "../../api/client";

const rejectionReasons = [
  ["too_expensive", "Too expensive"],
  ["missing_feature", "Missing a feature"],
  ["too_large", "Too large"],
  ["appearance", "Appearance"],
  ["weak_evidence", "Weak evidence"],
  ["wrong_category", "Wrong category"],
  ["already_owned", "Already owned"],
  ["other", "Other"],
] as const;

function requestKey() {
  return globalThis.crypto?.randomUUID?.() ?? `decision-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : "The decision could not be saved.";
}

export function ProductDecisionActions({
  project,
  projectProductId,
}: {
  project: Project;
  projectProductId: string;
}) {
  const queryClient = useQueryClient();
  const [rejectionReason, setRejectionReason] = useState<DecisionCommand["rejection_reason"]>("other");
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const decisionKey = ["decision", project.id, projectProductId] as const;
  const decisionQuery = useQuery({
    queryKey: decisionKey,
    queryFn: ({ signal }) => decisionsApi.get(project.id, projectProductId, signal),
    retry: false,
  });

  const mutation = useMutation({
    mutationFn: ({ state, command }: { state: "shortlisted" | "rejected" | "considering" | "purchased" | "set_purchased"; command: DecisionCommand }) => {
      if (state === "shortlisted") return decisionsApi.shortlist(project.id, projectProductId, command);
      if (state === "rejected") return decisionsApi.reject(project.id, projectProductId, command);
      if (state === "set_purchased") return decisionsApi.purchased(project.id, projectProductId, command);
      if (decisionQuery.data?.state === "purchased") {
        return decisionsApi.undoPurchased(project.id, projectProductId, command);
      }
      if (decisionQuery.data?.state === "rejected") {
        return decisionsApi.undoRejection(project.id, projectProductId, command);
      }
      return decisionsApi.undoShortlist(project.id, projectProductId, command);
    },
    onSuccess: async () => {
      setError("");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: decisionKey }),
        queryClient.invalidateQueries({ queryKey: ["project", project.id] }),
        queryClient.invalidateQueries({ queryKey: ["shortlist", project.id] }),
        queryClient.invalidateQueries({ queryKey: ["rejections", project.id] }),
        queryClient.invalidateQueries({ queryKey: ["project-comparisons", project.id] }),
      ]);
    },
    onError: (caught) => {
      setError(errorMessage(caught));
      if (caught instanceof ApiRequestError && caught.status === 409) {
        void queryClient.invalidateQueries({ queryKey: ["project", project.id] });
        void queryClient.invalidateQueries({ queryKey: decisionKey });
      }
    },
  });

  function send(state: "shortlisted" | "rejected" | "considering" | "purchased" | "set_purchased", selectedReason?: DecisionCommand["rejection_reason"]) {
    const command: DecisionCommand = {
      expected_version: project.revision,
      request_key: requestKey(),
      reason: reason.trim(),
      ...(state === "rejected" ? { rejection_reason: selectedReason ?? "other" } : {}),
      concerns: [],
    };
    mutation.mutate({ state, command });
  }

  function submitRejection(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    send("rejected", rejectionReason);
  }

  const decision = decisionQuery.data;
  const busy = mutation.isPending;
  return (
    <section className="decision-actions" aria-label="Product decision">
      {decisionQuery.isPending ? (
        <p role="status">Loading decision…</p>
      ) : decisionQuery.isError ? (
        <p className="field-error" role="alert">Decision state could not load.</p>
      ) : (
        <>
          <p className="decision-state-label">
            Decision: <strong>{decision?.state.replaceAll("_", " ") ?? "considering"}</strong>
            {decision?.rejection_reason && ` · ${rejectionReasons.find(([key]) => key === decision.rejection_reason)?.[1] ?? decision.rejection_reason}`}
          </p>
          {decision?.state === "purchased" ? (
            <button className="button quiet-button small-button" type="button" disabled={busy} onClick={() => send("considering")}>
              {busy ? "Saving…" : "Undo purchased state"}
            </button>
          ) : (
            <div className="decision-button-row">
              {decision?.state === "shortlisted" ? (
                <button className="button quiet-button small-button" type="button" disabled={busy} onClick={() => send("considering")}>
                  {busy ? "Saving…" : "Remove from shortlist"}
                </button>
              ) : (
                <button className="button primary-button small-button" type="button" disabled={busy} onClick={() => send("shortlisted")}>
                  {busy ? "Saving…" : "Shortlist"}
                </button>
              )}
              {decision?.state === "rejected" && (
                <button className="button quiet-button small-button" type="button" disabled={busy} onClick={() => send("considering")}>
                  Undo rejection
                </button>
              )}
              <button className="button quiet-button small-button" type="button" disabled={busy} onClick={() => send("set_purchased")}>
                {busy ? "Saving…" : "Mark as purchased"}
              </button>
            </div>
          )}
          {decision?.state !== "purchased" && decision?.state !== "rejected" && (
            <details className="reject-product-details">
              <summary>Reject this product</summary>
              <form onSubmit={submitRejection}>
                <label className="field-label">
                  Reason
                  <select
                    value={rejectionReason ?? "other"}
                    onChange={(event) => setRejectionReason(event.target.value as DecisionCommand["rejection_reason"])}
                    disabled={busy}
                  >
                    {rejectionReasons.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                  </select>
                </label>
                <label className="field-label">
                  Note (optional)
                  <textarea value={reason} maxLength={2000} onChange={(event) => setReason(event.target.value)} disabled={busy} />
                </label>
                <button className="button quiet-button small-button" type="submit" disabled={busy}>
                  {busy ? "Saving…" : "Save rejection"}
                </button>
              </form>
            </details>
          )}
          {decision?.events?.length ? (
            <details className="decision-history">
              <summary>Decision history ({decision.events.length})</summary>
              <ol>
                {decision.events.map((event) => (
                  <li key={event.id}>
                    <span>{event.from_state} → {event.to_state}</span>
                    <small>{event.actor === "assistant" ? "Assistant suggestion applied" : "You"} · {new Date(event.created_at).toLocaleString()}</small>
                    {event.reason && <small>{event.reason}</small>}
                  </li>
                ))}
              </ol>
            </details>
          ) : null}
        </>
      )}
      {error && <p className="field-error" role="alert">{error}</p>}
    </section>
  );
}
