import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import {
  ApiRequestError,
  PreferencePatch,
  PreferenceRead,
  PreferenceCandidateRead,
  ProfileRead,
  preferencesApi,
} from "../../api/client";

function errorText(error: unknown): string {
  if (error instanceof ApiRequestError && error.status === 409) {
    return `${error.message} Reload the profile and try again.`;
  }
  return error instanceof Error ? error.message : "The request could not be completed.";
}

export function PreferenceProfilePage() {
  const queryClient = useQueryClient();
  const profile = useQuery({
    queryKey: ["shopping-profile"],
    queryFn: () => preferencesApi.profile(),
    retry: false,
  });
  const [problem, setProblem] = useState("");

  const refreshProfile = async (updated: ProfileRead) => {
    queryClient.setQueryData(["shopping-profile"], updated);
    setProblem("");
  };

  const updateReuse = useMutation({
    mutationFn: (enabled: boolean) => {
      if (!profile.data) throw new Error("Shopping profile is unavailable.");
      return preferencesApi.patchProfile({ expected_version: profile.data.revision, reuse_enabled: enabled });
    },
    onSuccess: refreshProfile,
    onError: (error) => setProblem(errorText(error)),
  });
  const accept = useMutation({
    mutationFn: (candidateId: string) => {
      if (!profile.data) throw new Error("Shopping profile is unavailable.");
      return preferencesApi.acceptCandidate(candidateId, profile.data.revision);
    },
    onSuccess: async () => {
      setProblem("");
      await queryClient.invalidateQueries({ queryKey: ["shopping-profile"] });
    },
    onError: (error) => setProblem(errorText(error)),
  });
  const dismiss = useMutation({
    mutationFn: (candidateId: string) => {
      if (!profile.data) throw new Error("Shopping profile is unavailable.");
      return preferencesApi.dismissCandidate(candidateId, profile.data.revision);
    },
    onSuccess: async () => {
      setProblem("");
      await queryClient.invalidateQueries({ queryKey: ["shopping-profile"] });
    },
    onError: (error) => setProblem(errorText(error)),
  });
  const revoke = useMutation({
    mutationFn: (preferenceId: string) => {
      if (!profile.data) throw new Error("Shopping profile is unavailable.");
      return preferencesApi.revokePreference(preferenceId, profile.data.revision);
    },
    onSuccess: refreshProfile,
    onError: (error) => setProblem(errorText(error)),
  });

  return (
    <main className="shell profile-shell">
      <header className="app-header">
        <Link className="brand" to="/" aria-label="Shopping Assistant home">
          <span className="brand-mark" aria-hidden="true">S</span>
          <span>Shopping Assistant</span>
        </Link>
        <Link className="header-back" to="/">All projects <span aria-hidden="true">↗</span></Link>
      </header>
      <nav aria-label="Breadcrumb" className="breadcrumbs"><Link to="/">Projects</Link><span aria-hidden="true">/</span><span>Shopping Profile</span></nav>
      <div className="profile-title">
        <p className="eyebrow">Your shopping context</p>
        <h1>Shopping Profile</h1>
        <p>Preferences are suggestions for projects you choose. Project requirements and decisions stay local unless you promote a preference here.</p>
      </div>

      {profile.isPending && <p className="quiet-state" role="status">Loading your profile…</p>}
      {profile.isError && (
        <div className="notice error-notice" role="alert">
          <p>Your shopping profile could not load.</p>
          <button className="button quiet-button" type="button" onClick={() => void profile.refetch()}>Retry</button>
        </div>
      )}
      {problem && <p className="notice error-notice" role="alert">{problem}</p>}

      {profile.data && (
        <>
          <section className="card profile-settings-card" aria-labelledby="reuse-title">
            <div>
              <p className="eyebrow">Local reuse</p>
              <h2 id="reuse-title">Use profile preferences for project suggestions</h2>
              <p>Turn this off to stop profile preferences from appearing in any project. Existing project requirements remain as saved.</p>
            </div>
            <label className="check-row profile-switch">
              <input
                type="checkbox"
                checked={profile.data.reuse_enabled}
                disabled={updateReuse.isPending}
                onChange={(event) => updateReuse.mutate(event.target.checked)}
              />
              <span>{profile.data.reuse_enabled ? "Enabled" : "Disabled"}</span>
            </label>
          </section>

          <section className="card profile-section" aria-labelledby="candidates-title">
            <div className="section-heading">
              <span className="step-mark" aria-hidden="true">01</span>
              <div><p className="eyebrow">Review first</p><h2 id="candidates-title">Preference candidates</h2></div>
              <span className="count-pill">{profile.data.candidates.filter((item) => item.status === "pending").length}</span>
            </div>
            {profile.data.candidates.length === 0 && <p className="quiet-state">No candidates yet. In a project, propose a saved preference or select a rejected product judgment for review.</p>}
            <ul className="profile-list">
              {profile.data.candidates.map((candidate) => (
                <CandidateCard
                  key={candidate.id}
                  candidate={candidate}
                  profile={profile.data!}
                  busy={accept.isPending || dismiss.isPending}
                  onAccept={() => accept.mutate(candidate.id)}
                  onDismiss={() => dismiss.mutate(candidate.id)}
                />
              ))}
            </ul>
          </section>

          <section className="card profile-section" aria-labelledby="preferences-title">
            <div className="section-heading">
              <span className="step-mark" aria-hidden="true">02</span>
              <div><p className="eyebrow">Editable, scoped, revocable</p><h2 id="preferences-title">Shopping preferences</h2></div>
              <span className="count-pill">{profile.data.preferences.length}</span>
            </div>
            {profile.data.preferences.length === 0 && <p className="quiet-state">Accepted preferences will appear here with their source and revision.</p>}
            <ul className="profile-list">
              {profile.data.preferences.map((preference) => (
                <PreferenceCard
                  key={preference.id}
                  preference={preference}
                  profile={profile.data!}
                  onSaved={refreshProfile}
                  onProblem={setProblem}
                  onRevoke={() => revoke.mutate(preference.id)}
                  busy={revoke.isPending}
                />
              ))}
            </ul>
          </section>

          <section className="notice external-memory-note" aria-label="External memory status">
            <p className="eyebrow">Cross-application memory</p>
            <p>External Personal AI memory is unavailable because this app has no verified memory API contract. Your shopping profile works locally; no external memory writes occur.</p>
          </section>
        </>
      )}
    </main>
  );
}

function CandidateCard({
  candidate,
  profile,
  busy,
  onAccept,
  onDismiss,
}: {
  candidate: PreferenceCandidateRead;
  profile: ProfileRead;
  busy: boolean;
  onAccept: () => void;
  onDismiss: () => void;
}) {
  const stale = candidate.source_stale || candidate.status === "stale";
  return (
    <li className="profile-list-item">
      <div className="profile-card-heading">
        <div><span className={`status-pill ${candidate.status === "pending" && stale ? "status-archived" : ""}`}>{stale ? "stale source" : candidate.status}</span><h3>{candidate.label}</h3></div>
        <span className="scope-pill">{candidate.category_scopes.includes("*") ? "All categories" : candidate.category_scopes.join(", ")}</span>
      </div>
      <p className="profile-value">{candidate.key}{candidate.operator ? ` ${candidate.operator}` : ""}: {formatValue(candidate.value)}{candidate.unit ? ` ${candidate.unit}` : ""}</p>
      <p className="field-help">
        Origin: {candidate.source_kind === "decision" ? "rejected product judgment" : "project preference"} · {candidate.source_available ? <Link to={`/projects/${candidate.source_project_id}`}>{candidate.source_project_title}</Link> : "source unavailable"}
        {candidate.source_available ? ` · project revision ${candidate.source_project_revision}` : ""}
      </p>
      {candidate.rationale && <p>{candidate.rationale}</p>}
      {candidate.status === "pending" && !stale && profile.revision > 0 && (
        <div className="profile-actions">
          <button className="button small-button primary-button" type="button" disabled={busy} onClick={onAccept}>Accept into profile</button>
          <button className="button small-button quiet-button" type="button" disabled={busy} onClick={onDismiss}>Dismiss</button>
        </div>
      )}
      {stale && candidate.status === "pending" && <p className="field-help">The source project changed. Re-propose from its current version to confirm this scope again.</p>}
    </li>
  );
}

function PreferenceCard({
  preference,
  profile,
  onSaved,
  onProblem,
  onRevoke,
  busy,
}: {
  preference: PreferenceRead;
  profile: ProfileRead;
  onSaved: (profile: ProfileRead) => void;
  onProblem: (message: string) => void;
  onRevoke: () => void;
  busy: boolean;
}) {
  const queryClient = useQueryClient();
  const [label, setLabel] = useState(preference.label);
  const [key, setKey] = useState(preference.key);
  const [operator, setOperator] = useState<NonNullable<PreferenceRead["operator"]> | "">(preference.operator ?? "");
  const [value, setValue] = useState(JSON.stringify(preference.value, null, 2));
  const [unit, setUnit] = useState(preference.unit);
  const [scopes, setScopes] = useState(preference.category_scopes.join(", "));
  const edit = useMutation({
    mutationFn: (command: PreferencePatch) => preferencesApi.patchPreference(preference.id, command),
    onSuccess: async (updated) => {
      onSaved(updated);
      await queryClient.invalidateQueries({ queryKey: ["shopping-profile"] });
    },
    onError: (error) => onProblem(errorText(error)),
  });

  function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    let parsed: unknown;
    try { parsed = JSON.parse(value); } catch { onProblem("Enter a valid JSON value for this preference."); return; }
    const command: PreferencePatch = {
      expected_profile_version: profile.revision,
      expected_preference_revision: preference.revision,
      label: label.trim(),
      key: key.trim(),
      operator: operator || null,
      value: parsed,
      unit: unit.trim(),
      category_scopes: scopes.split(",").map((item) => item.trim()).filter(Boolean),
    };
    edit.mutate(command);
  }

  function reactivate() {
    edit.mutate({
      expected_profile_version: profile.revision,
      expected_preference_revision: preference.revision,
      status: "active",
    });
  }

  return (
    <li className="profile-list-item">
      <div className="profile-card-heading">
        <div><span className={`status-pill ${preference.status === "active" ? "status-active" : "status-archived"}`}>{preference.status}</span><h3>{preference.label}</h3></div>
        <span className="scope-pill">{preference.category_scopes.includes("*") ? "All categories" : preference.category_scopes.join(", ")}</span>
      </div>
      <p className="profile-value">{preference.key}{preference.operator ? ` ${preference.operator}` : ""}: {formatValue(preference.value)}{preference.unit ? ` ${preference.unit}` : ""}</p>
      <p className="field-help">
        Origin: {preference.source_kind === "decision" ? "rejected product judgment" : "project preference"} · {preference.source_available ? <Link to={`/projects/${preference.source_project_id}`}>{preference.source_project_title}</Link> : "source unavailable"}
        {` · preference revision ${preference.revision}`}
      </p>
      <details className="preference-edit">
        <summary>Edit preference</summary>
        <form onSubmit={save}>
          <label className="field-label" htmlFor={`edit-pref-label-${preference.id}`}>Label</label>
          <input id={`edit-pref-label-${preference.id}`} value={label} maxLength={300} required onChange={(event) => setLabel(event.target.value)} />
          <div className="field-grid">
            <div><label className="field-label" htmlFor={`edit-pref-key-${preference.id}`}>Key</label><input id={`edit-pref-key-${preference.id}`} value={key} maxLength={100} required onChange={(event) => setKey(event.target.value)} /></div>
            <div>
              <label className="field-label" htmlFor={`edit-pref-operator-${preference.id}`}>Operator</label>
              <select id={`edit-pref-operator-${preference.id}`} value={operator} onChange={(event) => setOperator(event.target.value as NonNullable<PreferenceRead["operator"]> | "")}>
                <option value="">None</option>{(["eq", "gte", "lte", "contains", "one_of"] as const).map((item) => <option key={item} value={item}>{item}</option>)}
              </select>
            </div>
          </div>
          <label className="field-label" htmlFor={`edit-pref-value-${preference.id}`}>Value (JSON)</label>
          <textarea id={`edit-pref-value-${preference.id}`} value={value} rows={2} required onChange={(event) => setValue(event.target.value)} />
          <label className="field-label" htmlFor={`edit-pref-unit-${preference.id}`}>Unit or currency</label>
          <input id={`edit-pref-unit-${preference.id}`} value={unit} maxLength={50} onChange={(event) => setUnit(event.target.value)} />
          <label className="field-label" htmlFor={`edit-pref-scopes-${preference.id}`}>Categories (comma separated; use * for all)</label>
          <input id={`edit-pref-scopes-${preference.id}`} value={scopes} required onChange={(event) => setScopes(event.target.value)} />
          <div className="profile-actions">
            <button className="button small-button secondary-button" type="submit" disabled={edit.isPending}>{edit.isPending ? "Saving…" : "Save edits"}</button>
            {preference.status === "active" ? <button className="button small-button text-danger-button" type="button" disabled={busy} onClick={onRevoke}>Revoke</button> : <button className="button small-button quiet-button" type="button" disabled={edit.isPending} onClick={reactivate}>Reactivate</button>}
          </div>
        </form>
      </details>
    </li>
  );
}

function formatValue(value: unknown): string {
  if (typeof value === "string") return value;
  return JSON.stringify(value);
}
