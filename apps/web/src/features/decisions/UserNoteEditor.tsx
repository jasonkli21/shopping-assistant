import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiRequestError, Project, notesApi } from "../../api/client";
import { invalidateProjectWorkspace } from "../assistant/workspace-cache";

export function UserNoteEditor({
  project,
  projectProductId,
  title = "Your note",
}: {
  project: Project;
  projectProductId?: string;
  title?: string;
}) {
  const queryClient = useQueryClient();
  const noteKey = ["user-note", project.id, projectProductId ?? "project"] as const;
  const targetKey = `${project.id}:${projectProductId ?? "project"}`;
  const activeTarget = useRef(targetKey);
  const noteQuery = useQuery({
    queryKey: noteKey,
    queryFn: ({ signal }) => notesApi.get(project.id, projectProductId, signal),
    retry: false,
  });
  const [draft, setDraft] = useState("");
  const [edited, setEdited] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (activeTarget.current === targetKey) return;
    activeTarget.current = targetKey;
    setDraft("");
    setEdited(false);
    setError("");
    setSaved(false);
  }, [targetKey]);

  useEffect(() => {
    if (!edited && noteQuery.isSuccess) setDraft(noteQuery.data?.text ?? "");
  }, [edited, noteQuery.data, noteQuery.isSuccess]);

  const save = useMutation({
    mutationFn: (variables: { projectId: string; projectProductId?: string; expectedVersion: number; text: string; targetKey: string }) => notesApi.put(variables.projectId, {
      expected_version: variables.expectedVersion,
      text: variables.text,
    }, variables.projectProductId),
    onSuccess: async ({ note }, variables) => {
      queryClient.setQueryData(["user-note", variables.projectId, variables.projectProductId ?? "project"], note);
      if (activeTarget.current === variables.targetKey) {
        setDraft(note.text);
        setEdited(false);
        setSaved(true);
        setError("");
      }
      await invalidateProjectWorkspace(queryClient, variables.projectId);
    },
    onError: (caught, variables) => {
      if (activeTarget.current === variables.targetKey) {
        setSaved(false);
        setError(caught instanceof Error ? caught.message : "Your note could not be saved.");
      }
      if (caught instanceof ApiRequestError && caught.status === 409) {
        void invalidateProjectWorkspace(queryClient, variables.projectId);
      }
    },
  });

  const remove = useMutation({
    mutationFn: (variables: { projectId: string; projectProductId?: string; expectedVersion: number; targetKey: string }) => notesApi.delete(variables.projectId, variables.expectedVersion, variables.projectProductId),
    onSuccess: async (_result, variables) => {
      queryClient.setQueryData(["user-note", variables.projectId, variables.projectProductId ?? "project"], null);
      if (activeTarget.current === variables.targetKey) {
        setDraft("");
        setEdited(false);
        setSaved(false);
        setError("");
      }
      await invalidateProjectWorkspace(queryClient, variables.projectId);
    },
    onError: (caught, variables) => {
      if (activeTarget.current === variables.targetKey) {
        setError(caught instanceof Error ? caught.message : "Your note could not be deleted.");
      }
      if (caught instanceof ApiRequestError && caught.status === 409) {
        void invalidateProjectWorkspace(queryClient, variables.projectId);
      }
    },
  });

  const busy = save.isPending || remove.isPending;
  return (
    <section className="user-note-editor" aria-label={title}>
      <label className="field-label">
        {title}
        <textarea
          value={draft}
          maxLength={10000}
          rows={4}
          placeholder="Keep a rationale or concern for this decision."
          disabled={busy}
          onChange={(event) => {
            setDraft(event.target.value);
            setEdited(true);
            setSaved(false);
            setError("");
          }}
        />
      </label>
      {noteQuery.isError && <p className="field-error" role="alert">Saved note could not load.</p>}
      {error && <p className="field-error" role="alert">{error}</p>}
      {saved && <p className="decision-saved-message" role="status">Note saved.</p>}
      <div className="decision-button-row">
        <button
          className="button quiet-button small-button"
          type="button"
          disabled={busy || !draft.trim() || !edited}
          onClick={() => save.mutate({ projectId: project.id, projectProductId, expectedVersion: project.revision, text: draft.trim(), targetKey })}
        >
          {save.isPending ? "Saving…" : "Save note"}
        </button>
        {noteQuery.data && (
          <button
            className="button quiet-button small-button"
            type="button"
            disabled={busy}
            onClick={() => remove.mutate({ projectId: project.id, projectProductId, expectedVersion: project.revision, targetKey })}
          >
            {remove.isPending ? "Removing…" : "Delete note"}
          </button>
        )}
      </div>
    </section>
  );
}
