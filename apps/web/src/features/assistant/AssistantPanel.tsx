import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiRequestError, MessagePage, MessageRead, Project, ProposalRead, projectsApi } from "../../api/client";
import { PendingAttempt, clearPendingAttempt, persistPendingAttempt, readPendingAttempt } from "./attempt-storage";
import { handleStreamEvent, messageKey } from "./conversation-cache";
import { ProposalCard } from "./ProposalCard";
import { EvidenceCitation } from "./EvidenceCitation";

interface AssistantPanelProps {
  project: Project;
  selectedProjectProductIds?: string[];
  comparisonId?: string;
  blocked?: boolean;
  onProjectUpdate: (project: Project, replayed: boolean) => void;
  onRevisionConflict: (error: unknown) => Promise<unknown>;
  onProposalActionPendingChange?: (pending: boolean) => void;
}

export function AssistantPanel({
  project,
  selectedProjectProductIds,
  comparisonId,
  blocked = false,
  onProjectUpdate,
  onRevisionConflict,
  onProposalActionPendingChange = () => {},
}: AssistantPanelProps) {
  const queryClient = useQueryClient();
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const toggleRef = useRef<HTMLButtonElement>(null);
  const attemptedStreams = useRef(new Set<string>());
  const [isOpen, setIsOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const [pendingAttempt, setPendingAttempt] = useState<PendingAttempt | null>(() =>
    readPendingAttempt(project.id),
  );
  const [sending, setSending] = useState(false);
  const [activeMessageId, setActiveMessageId] = useState<string | null>(null);
  const [streaming, setStreaming] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [proposalActionId, setProposalActionId] = useState<string | null>(null);
  const [loadingOlder, setLoadingOlder] = useState(false);

  const history = useQuery({
    queryKey: messageKey(project.id),
    queryFn: () => projectsApi.listMessages(project.id, 100),
    enabled: isOpen,
    retry: false,
    refetchOnWindowFocus: false,
  });
  const messages = useMemo(() => history.data?.items ?? [], [history.data]);

  useEffect(() => {
    if (isOpen) textareaRef.current?.focus();
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") closeAssistant();
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [isOpen]);

  useEffect(() => {
    if (pendingAttempt) return;
    const unfinished = [...messages].reverse().find(
      (item) => item.role === "assistant" && item.status === "generating",
    );
    if (unfinished && !attemptedStreams.current.has(unfinished.id)) {
      attemptedStreams.current.add(unfinished.id);
      setActiveMessageId(unfinished.id);
    }
  }, [messages, pendingAttempt]);

  useEffect(() => {
    if (!pendingAttempt || !history.data) return;
    const savedUserMessage = history.data.items.find(
      (message) => message.role === "user" && message.request_key === pendingAttempt.requestKey,
    );
    if (!savedUserMessage) return;
    clearPendingAttempt(project.id);
    setPendingAttempt(null);
    setNotice("Your saved message was found in history. Reconnecting to its response.");
    if (savedUserMessage.paired_message_id) {
      attemptedStreams.current.add(savedUserMessage.paired_message_id);
      setActiveMessageId(savedUserMessage.paired_message_id);
    }
  }, [history.data, pendingAttempt, project.id]);

  useEffect(() => {
    if (!activeMessageId) return;
    const controller = new AbortController();
    setStreaming(true);
    setError("");
    setNotice("Connected to the saved assistant response.");
    void projectsApi
      .streamMessage(
        project.id,
        activeMessageId,
        (event) => handleStreamEvent(event.event, event.data, queryClient, project.id),
        controller.signal,
      )
      .then((terminal) => {
        void queryClient.invalidateQueries({ queryKey: messageKey(project.id) });
        if (!terminal && !controller.signal.aborted) {
          setError("The connection ended before a final status arrived. Reload history or reconnect to the saved response.");
        }
        setActiveMessageId(null);
      })
      .catch((caught: unknown) => {
        if (controller.signal.aborted) return;
        setError(caught instanceof Error ? caught.message : "The assistant connection ended.");
        void queryClient.invalidateQueries({ queryKey: messageKey(project.id) });
        setActiveMessageId(null);
      })
      .finally(() => setStreaming(false));
    return () => controller.abort();
  }, [activeMessageId, project.id, queryClient]);

  async function submitMessage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!draft.trim() || sending || pendingAttempt || blocked) return;
    const attempt: PendingAttempt = {
      text: draft.trim(),
      requestKey: crypto.randomUUID(),
      expectedVersion: project.revision,
      selectedProjectProductIds,
      comparisonId,
    };
    setPendingAttempt(attempt);
    persistPendingAttempt(project.id, attempt);
    await sendAttempt(attempt);
  }

  async function sendAttempt(attempt: PendingAttempt) {
    setSending(true);
    setError("");
    setNotice("Sending your message…");
    try {
      const response = await projectsApi.createMessage(project.id, {
        text: attempt.text,
        request_key: attempt.requestKey,
        expected_version: attempt.expectedVersion,
        selected_project_product_ids: attempt.selectedProjectProductIds ?? [],
        comparison_id: attempt.comparisonId ?? null,
      });
      clearPendingAttempt(project.id);
      setPendingAttempt(null);
      setDraft("");
      setNotice(
        response.replayed
          ? "The same saved command was confirmed. Reconnecting to its response."
          : "Message saved. Preparing suggestions for review.",
      );
      attemptedStreams.current.add(response.assistant_message_id);
      setActiveMessageId(response.assistant_message_id);
      void queryClient.invalidateQueries({ queryKey: messageKey(project.id) });
    } catch (caught) {
      setNotice("");
      if (
        caught instanceof ApiRequestError &&
        (caught.code === "revision_conflict" || caught.code === "proposal_stale")
      ) {
        clearPendingAttempt(project.id);
        setPendingAttempt(null);
        setDraft(attempt.text);
        setError("The project changed before this message was accepted. Review the refreshed project, then send your saved text again.");
        await onRevisionConflict(caught);
      } else if (caught instanceof ApiRequestError && caught.status === 422) {
        clearPendingAttempt(project.id);
        setPendingAttempt(null);
        setDraft(attempt.text);
        setError(caught.message);
      } else if (
        caught instanceof ApiRequestError &&
        ((caught.status === 409 && caught.code === "conversation_busy") ||
          (caught.status === 503 && caught.code === "generation_capacity"))
      ) {
        clearPendingAttempt(project.id);
        setPendingAttempt(null);
        setDraft(attempt.text);
        setError(
          caught.code === "conversation_busy"
            ? "Another assistant response is still being prepared. Your message was not saved. Try again when it finishes."
            : "The assistant is busy right now. Your message was not saved. Try again shortly.",
        );
      } else {
        setPendingAttempt(attempt);
        persistPendingAttempt(project.id, attempt);
        setError("We could not confirm whether the message was saved. Retry this same submission to safely recover it.");
      }
      void queryClient.invalidateQueries({ queryKey: messageKey(project.id) });
    } finally {
      setSending(false);
    }
  }

  async function loadOlderMessages() {
    const cursor = history.data?.next_cursor;
    if (!cursor || loadingOlder) return;
    setLoadingOlder(true);
    try {
      const olderPage = await projectsApi.listMessages(project.id, 100, cursor);
      queryClient.setQueryData<MessagePage>(messageKey(project.id), (current) => {
        if (!current) return olderPage;
        const uniqueMessages = new Map(
          [...olderPage.items, ...current.items].map((message) => [message.id, message]),
        );
        return {
          items: [...uniqueMessages.values()].sort((left, right) => left.ordinal - right.ordinal),
          next_cursor: olderPage.next_cursor,
        };
      });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Earlier messages could not be loaded.");
    } finally {
      setLoadingOlder(false);
    }
  }

  function closeAssistant() {
    setIsOpen(false);
    toggleRef.current?.focus();
  }

  async function applyProposal(proposal: ProposalRead) {
    if (proposalActionId) return;
    setProposalActionId(proposal.id);
    onProposalActionPendingChange(true);
    setError("");
    try {
      const result = await projectsApi.applyProposal(
        project.id,
        proposal.id,
        project.revision,
      );
      if (result.project) onProjectUpdate(result.project, result.replayed);
      setNotice(
        result.replayed
          ? `This suggestion was already applied at revision ${result.proposal.applied_revision}.`
          : `Suggestion applied at revision ${result.project?.revision}.`,
      );
      void queryClient.invalidateQueries({ queryKey: messageKey(project.id) });
    } catch (caught) {
      if (
        caught instanceof ApiRequestError &&
        (caught.code === "revision_conflict" || caught.code === "proposal_stale")
      ) {
        await onRevisionConflict(caught);
        setError("The project changed after this suggestion was prepared. Review the latest project and ask the assistant for a fresh suggestion.");
      } else {
        setError(caught instanceof Error ? caught.message : "The suggestion could not be applied.");
      }
      void queryClient.invalidateQueries({ queryKey: messageKey(project.id) });
    } finally {
      setProposalActionId(null);
      onProposalActionPendingChange(false);
    }
  }

  async function dismissProposal(proposal: ProposalRead) {
    if (proposalActionId) return;
    setProposalActionId(proposal.id);
    onProposalActionPendingChange(true);
    setError("");
    try {
      await projectsApi.dismissProposal(project.id, proposal.id);
      setNotice("Suggestion dismissed. Your project was not changed.");
      void queryClient.invalidateQueries({ queryKey: messageKey(project.id) });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The suggestion could not be dismissed.");
    } finally {
      setProposalActionId(null);
      onProposalActionPendingChange(false);
    }
  }

  function retryFailedMessage(message: MessageRead) {
    const original = messages.find((item) => item.id === message.paired_message_id);
    if (!original) return;
    setDraft(original.text);
    setError("");
    setNotice("Edit the saved text if needed, then send it as a new message.");
    textareaRef.current?.focus();
  }

  function reconnect(message: MessageRead) {
    attemptedStreams.current.add(message.id);
    setActiveMessageId(message.id);
  }

  return (
    <div className={`assistant-dock${isOpen ? " assistant-dock-open" : ""}`}>
      {isOpen && <button className="assistant-backdrop" type="button" aria-label="Close assistant" onClick={closeAssistant} />}
      <button
        ref={toggleRef}
        className="button primary-button assistant-toggle"
        type="button"
        aria-expanded={isOpen}
        aria-controls="project-assistant-panel"
        onClick={() => (isOpen ? closeAssistant() : setIsOpen(true))}
      >
        {isOpen ? "Close assistant" : "Ask assistant"}
        {!isOpen && messages.length > 0 && <span className="assistant-toggle-count">{messages.length}</span>}
      </button>

      {isOpen && (
        <section id="project-assistant-panel" className="assistant-panel" aria-labelledby="assistant-title">
          <header className="assistant-header">
            <div>
              <p className="eyebrow">Project assistant</p>
              <h2 id="assistant-title">Refine your intent</h2>
            </div>
            <button className="button quiet-button small-button" type="button" onClick={closeAssistant}>
              Close
            </button>
          </header>

          <div className="assistant-history" aria-live="polite" aria-relevant="additions text">
            {history.data?.next_cursor && (
              <button
                className="button quiet-button small-button assistant-load-older"
                type="button"
                disabled={loadingOlder}
                onClick={() => void loadOlderMessages()}
              >
                {loadingOlder ? "Loading earlier messages…" : "Load earlier messages"}
              </button>
            )}
            {history.isLoading && <p className="quiet-state">Loading saved conversation…</p>}
            {history.isError && (
              <div className="notice error-notice" role="alert">
                <p>Saved conversation history could not be loaded.</p>
                <button className="button quiet-button small-button" type="button" onClick={() => void history.refetch()}>
                  Retry history
                </button>
              </div>
            )}
            {!history.isLoading && !history.isError && messages.length === 0 && (
              <div className="assistant-empty">
                <strong>Tell me what you’re shopping for.</strong>
                <p>I’ll ask about unclear details and show project suggestions for your approval.</p>
              </div>
            )}
            {messages.map((message) => (
              <article key={message.id} className={`assistant-message assistant-message-${message.role}`}>
                <p className="assistant-message-label">{message.role === "user" ? "You" : "Assistant"}</p>
                {message.text ? <p className="assistant-message-text">{message.text}</p> : null}
                {message.role === "assistant" && message.citation_ids?.length ? (
                  <div className="assistant-citations" aria-label="Cited evidence">
                    {message.citation_ids.map((claimId) => <EvidenceCitation key={claimId} projectId={project.id} claimId={claimId} />)}
                  </div>
                ) : null}
                {message.role === "assistant" && message.status === "generating" && (
                  <p className="assistant-pending" role="status">{streaming && activeMessageId === message.id ? "Preparing suggestions…" : "Response in progress"}</p>
                )}
                {message.role === "assistant" && message.clarification_questions?.length ? (
                  <ul className="assistant-questions">
                    {message.clarification_questions.map((question) => <li key={question}>{question}</li>)}
                  </ul>
                ) : null}
                {message.role === "assistant" && message.status === "failed" && (
                  <>
                    <p className="assistant-failure">{message.error_code ? describeFailure(message.error_code) : "The response failed."}</p>
                    <button className="button quiet-button small-button" type="button" onClick={() => retryFailedMessage(message)}>
                      Retry as a new message
                    </button>
                  </>
                )}
                {message.role === "assistant" && message.status === "interrupted" && (
                  <>
                    <p className="assistant-failure">The local service restarted before this response finished.</p>
                    <button className="button quiet-button small-button" type="button" onClick={() => retryFailedMessage(message)}>
                      Retry as a new message
                    </button>
                  </>
                )}
                {message.role === "assistant" && message.status === "generating" && !streaming && (
                  <button className="button quiet-button small-button" type="button" onClick={() => reconnect(message)}>
                    Reconnect to response
                  </button>
                )}
                {message.role === "assistant" && message.proposal && (
                  <ProposalCard
                    proposal={message.proposal}
                    project={project}
                    pending={proposalActionId === message.proposal.id}
                    blocked={blocked}
                    onApply={() => void applyProposal(message.proposal!)}
                    onDismiss={() => void dismissProposal(message.proposal!)}
                  />
                )}
              </article>
            ))}
          </div>

          {pendingAttempt && !sending && (
            <div className="assistant-acknowledgement" role="alert">
              <p>{error || "The saved command has not been confirmed."}</p>
              <button className="button secondary-button small-button" type="button" onClick={() => void sendAttempt(pendingAttempt)}>
                Retry same submission
              </button>
              <button className="button quiet-button small-button" type="button" onClick={() => void history.refetch()}>
                Check saved history
              </button>
            </div>
          )}
          {error && !pendingAttempt && <p className="assistant-inline-error" role="alert">{error}</p>}
          {notice && <p className="assistant-inline-notice" role="status">{notice}</p>}

          <form className="assistant-composer" onSubmit={submitMessage}>
            <label htmlFor="assistant-message">Your shopping request</label>
            <textarea
              ref={textareaRef}
              id="assistant-message"
              maxLength={8000}
              value={draft}
              disabled={sending || Boolean(pendingAttempt) || blocked}
              placeholder="I need a lightweight vacuum under $400…"
              onChange={(event) => setDraft(event.target.value)}
            />
            <div className="assistant-composer-footer">
              <span>{draft.length}/8000</span>
              <button className="button primary-button" type="submit" disabled={sending || Boolean(pendingAttempt) || blocked || !draft.trim()}>
                {sending ? "Saving…" : "Send"}
              </button>
            </div>
            <p className="assistant-disclosure">Suggestions remain pending until you apply them.</p>
            {blocked && <p className="assistant-disclosure">Save or reconcile your project edits before sending or applying suggestions.</p>}
          </form>
        </section>
      )}
    </div>
  );
}

function describeFailure(code: string) {
  const messages: Record<string, string> = {
    provider_unavailable: "Assistant suggestions are unavailable until the AI service is configured.",
    provider_timeout: "The assistant took too long to respond.",
    provider_refused: "The assistant could not process this request.",
    invalid_output: "The assistant response could not be validated. No project changes were made.",
    context_too_large: "The project context is too large to send safely.",
    generation_failed: "The assistant could not complete this response.",
  };
  return messages[code] ?? "The assistant could not complete this response.";
}
