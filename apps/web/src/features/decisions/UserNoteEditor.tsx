import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiRequestError, Project, notesApi } from "../../api/client";

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
    if (!edited && noteQuery.isSuccess) setDraft(noteQuery.data?.text ?? "");
  }, [edited, noteQuery.data, noteQuery.isSuccess]);

  const save = useMutation({
    mutationFn: () => notesApi.put(project.id, {
      expected_version: project.revision,
      text: draft.trim(),
    }, projectProductId),
    onSuccess: async ({ note }) => {
      queryClient.setQueryData(noteKey, note);
      setDraft(note.text);
      setEdited(false);
      setSaved(true);
      setError("");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["project", project.id] }),
        queryClient.invalidateQueries({ queryKey: ["project-comparisons", project.id] }),
      ]);
    },
    onError: (caught) => {
      setSaved(false);
      setError(caught instanceof Error ? caught.message : "Your note could not be saved.");
      if (caught instanceof ApiRequestError && caught.status === 409) {
        void queryClient.invalidateQueries({ queryKey: ["project", project.id] });
        void noteQuery.refetch();
      }
    },
  });

  const remove = useMutation({
    mutationFn: () => notesApi.delete(project.id, project.revision, projectProductId),
    onSuccess: async () => {
      queryClient.setQueryData(noteKey, null);
      setDraft("");
      setEdited(false);
      setSaved(false);
      setError("");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["project", project.id] }),
        queryClient.invalidateQueries({ queryKey: ["project-comparisons", project.id] }),
      ]);
    },
    onError: (caught) => {
      setError(caught instanceof Error ? caught.message : "Your note could not be deleted.");
      if (caught instanceof ApiRequestError && caught.status === 409) {
        void queryClient.invalidateQueries({ queryKey: ["project", project.id] });
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
          onClick={() => save.mutate()}
        >
          {save.isPending ? "Saving…" : "Save note"}
        </button>
        {noteQuery.data && (
          <button
            className="button quiet-button small-button"
            type="button"
            disabled={busy}
            onClick={() => remove.mutate()}
          >
            {remove.isPending ? "Removing…" : "Delete note"}
          </button>
        )}
      </div>
    </section>
  );
}
