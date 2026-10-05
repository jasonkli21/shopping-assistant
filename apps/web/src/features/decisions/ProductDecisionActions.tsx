import { FormEvent, useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  ApiRequestError,
  DecisionCommand,
  OfferRead,
  Project,
  decisionsApi,
} from "../../api/client";
import { invalidateProjectWorkspace } from "../assistant/workspace-cache";

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
  offers,
}: {
  project: Project;
  projectProductId: string;
  offers?: OfferRead[];
}) {
  const queryClient = useQueryClient();
  const [rejectionReason, setRejectionReason] = useState<DecisionCommand["rejection_reason"]>("other");
  const [reason, setReason] = useState("");
  const [reasonEdited, setReasonEdited] = useState(false);
  const [concernDraft, setConcernDraft] = useState("");
  const [concernsEdited, setConcernsEdited] = useState(false);
  const [offerDraft, setOfferDraft] = useState<string | null>(null);
  const [offerEdited, setOfferEdited] = useState(false);
  const [error, setError] = useState("");
  const decisionKey = ["decision", project.id, projectProductId] as const;
  const decisionQuery = useQuery({
    queryKey: decisionKey,
    queryFn: ({ signal }) => decisionsApi.get(project.id, projectProductId, signal),
    retry: false,
  });
  const decision = decisionQuery.data;

  useEffect(() => {
    if (!reasonEdited) setReason(decision?.reason ?? "");
  }, [decision?.reason, reasonEdited]);

  useEffect(() => {
    if (!concernsEdited) setConcernDraft(decision?.concerns.join("\n") ?? "");
  }, [decision?.concerns, concernsEdited]);

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
      setReasonEdited(false);
      setConcernsEdited(false);
      setOfferEdited(false);
      await invalidateProjectWorkspace(queryClient, project.id);
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
      reason: reasonEdited ? reason.trim() : decision?.reason ?? "",
      ...(state === "rejected" ? { rejection_reason: selectedReason ?? "other" } : {}),
      concerns: concernsEdited
        ? concernDraft.split("\n").map((item) => item.trim()).filter(Boolean).slice(0, 20)
        : decision?.concerns ?? [],
      selected_offer_id: offerEdited ? offerDraft : decision?.selected_offer_id ?? null,
    };
    mutation.mutate({ state, command });
  }

  function submitRejection(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    send("rejected", rejectionReason);
  }

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
          <label className="field-label">
            Rationale
            <textarea value={reason} maxLength={2000} onChange={(event) => { setReason(event.target.value); setReasonEdited(true); }} disabled={busy} />
          </label>
          <label className="field-label">
            Concerns <span className="optional">One per line</span>
            <textarea
              value={concernDraft}
              rows={2}
              onChange={(event) => { setConcernDraft(event.target.value); setConcernsEdited(true); }}
              disabled={busy}
            />
          </label>
          {offers && offers.length > 0 && (
            <label className="field-label">
              Selected offer
              <select
                value={offerEdited ? offerDraft ?? "" : decision?.selected_offer_id ?? ""}
                onChange={(event) => { setOfferDraft(event.target.value || null); setOfferEdited(true); }}
                disabled={busy}
              >
                <option value="">No selected offer</option>
                {decision?.selected_offer_id && !offers.some((offer) => offer.id === decision.selected_offer_id) && (
                  <option value={decision.selected_offer_id}>
                    Saved offer {decision.selected_offer_id.slice(0, 8)} (not in current list)
                  </option>
                )}
                {offers.map((offer) => <option key={offer.id} value={offer.id}>{offer.retailer_name} · {offer.amount && offer.currency ? `${offer.currency} ${offer.amount}` : "Price unknown"}</option>)}
              </select>
            </label>
          )}
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
                    {event.concerns?.length ? <small>Concerns: {event.concerns.join(" · ")}</small> : null}
                    {event.selected_offer_id && <small>Selected offer: {event.selected_offer_id}</small>}
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
