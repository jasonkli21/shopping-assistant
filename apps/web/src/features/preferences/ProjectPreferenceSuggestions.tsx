import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiRequestError, Project, preferencesApi, projectsApi } from "../../api/client";

export function ProjectPreferenceSuggestions({
  project,
  blocked,
  onProjectUpdate,
}: {
  project: Project;
  blocked: boolean;
  onProjectUpdate: (project: Project) => void;
}) {
  const queryClient = useQueryClient();
  const suggestions = useQuery({
    queryKey: ["preference-suggestions", project.id, project.revision],
    queryFn: () => preferencesApi.suggestions(project.id),
    enabled: project.reuse_preferences,
    retry: false,
  });
  const toggle = useMutation({
    mutationFn: (enabled: boolean) => projectsApi.patch(project.id, {
      expected_version: project.revision,
      reuse_preferences: enabled,
    }),
    onSuccess: async (updated) => {
      onProjectUpdate(updated);
      await queryClient.invalidateQueries({ queryKey: ["preference-suggestions", project.id] });
    },
  });
  const apply = useMutation({
    mutationFn: (preferenceId: string) => preferencesApi.applyToProject(project.id, preferenceId, project.revision),
    onSuccess: async (updated) => {
      onProjectUpdate(updated);
      await queryClient.invalidateQueries({ queryKey: ["preference-suggestions", project.id] });
    },
  });
  const error = toggle.error ?? apply.error ?? suggestions.error;

  return (
    <section className="card project-preferences-card" aria-labelledby="project-preferences-title">
      <div className="project-preferences-copy">
        <p className="eyebrow">Optional profile context</p>
        <h2 id="project-preferences-title">Shopping preferences</h2>
        <p>Profile preferences are suggestions. Choose each one to add it as an editable project requirement.</p>
        <p>Existing must-haves and constraints stay in force if they conflict with a soft preference.</p>
      </div>
      <label className="check-row project-reuse-toggle">
        <input
          type="checkbox"
          checked={project.reuse_preferences}
          disabled={blocked || toggle.isPending}
          onChange={(event) => toggle.mutate(event.target.checked)}
        />
        <span>Show applicable profile preferences in this project</span>
      </label>
      {!project.reuse_preferences && <p className="field-help">Profile preferences are off for this project.</p>}
      {project.reuse_preferences && !project.category && <p className="field-help">Set a project category to see category-scoped suggestions.</p>}
      {project.reuse_preferences && suggestions.isPending && <p className="quiet-state" role="status">Checking applicable preferences…</p>}
      {project.reuse_preferences && suggestions.isSuccess && suggestions.data.profile_reuse_enabled && suggestions.data.items.length === 0 && (
        <p className="quiet-state">No unapplied profile preferences match this project.</p>
      )}
      {project.reuse_preferences && suggestions.isSuccess && !suggestions.data.profile_reuse_enabled && (
        <p className="quiet-state">Profile reuse is disabled in Shopping Profile.</p>
      )}
      {project.reuse_preferences && suggestions.data?.items.length ? (
        <ul className="project-preference-list">
          {suggestions.data.items.map((preference) => (
            <li key={preference.id} className="project-preference-item">
              <div>
                <strong>{preference.label}</strong>
                <p>{preference.key}{preference.operator ? ` ${preference.operator}` : ""}: {formatValue(preference.value)}{preference.unit ? ` ${preference.unit}` : ""}</p>
                <small>From {preference.source_available ? preference.source_project_title : "an unavailable source"} · {preference.category_scopes.includes("*") ? "all categories" : preference.category_scopes.join(", ")}</small>
              </div>
              <button
                className="button small-button secondary-button"
                type="button"
                disabled={blocked || apply.isPending || toggle.isPending}
                onClick={() => apply.mutate(preference.id)}
              >{apply.isPending && apply.variables === preference.id ? "Adding…" : "Add to requirements"}</button>
            </li>
          ))}
        </ul>
      ) : null}
      {error && (
        <p className="notice error-notice" role="alert">
          {error instanceof ApiRequestError && error.status === 409
            ? `${error.message} Reload the project before trying again.`
            : error instanceof Error ? error.message : "Preference suggestions could not load."}
        </p>
      )}
    </section>
  );
}

function formatValue(value: unknown): string {
  return typeof value === "string" ? value : JSON.stringify(value);
}
