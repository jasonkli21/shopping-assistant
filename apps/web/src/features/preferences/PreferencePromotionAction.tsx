import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiRequestError, Project, Requirement, preferencesApi } from "../../api/client";

type PreferencePromotionActionProps =
  | {
      project: Project;
      requirement: Requirement;
      sourceProjectProductId?: never;
      initialLabel?: never;
      initialValue?: never;
      initialRationale?: never;
    }
  | {
      project: Project;
      requirement?: never;
      sourceProjectProductId: string;
      initialLabel: string;
      initialValue: string;
      initialRationale: string;
    };

export function PreferencePromotionAction({
  project,
  requirement,
  sourceProjectProductId,
  initialLabel,
  initialValue,
  initialRationale,
}: PreferencePromotionActionProps) {
  const sourceId = requirement?.id ?? sourceProjectProductId!;
  const sourceLabel = requirement?.label ?? initialLabel!;
  const sourceVersion = JSON.stringify([project.revision, requirement ?? [initialLabel, initialValue, initialRationale]]);
  const queryClient = useQueryClient();
  const [baseSourceVersion, setBaseSourceVersion] = useState(sourceVersion);
  const [label, setLabel] = useState(sourceLabel);
  const [key, setKey] = useState(requirement?.attribute_key ?? "statement");
  const [operator, setOperator] = useState<NonNullable<Requirement["operator"]> | "">(requirement?.operator ?? "");
  const [value, setValue] = useState(
    requirement
      ? requirement.value == null ? JSON.stringify(requirement.label) : JSON.stringify(requirement.value, null, 2)
      : JSON.stringify(initialValue),
  );
  const [unit, setUnit] = useState(requirement?.unit ?? "");
  const [monetary, setMonetary] = useState(false);
  const [scopes, setScopes] = useState(project.category ?? "");
  const [allCategories, setAllCategories] = useState(false);
  const [message, setMessage] = useState("");
  const [problem, setProblem] = useState("");

  function reloadDraft() {
    setLabel(sourceLabel);
    setKey(requirement?.attribute_key ?? "statement");
    setOperator(requirement?.operator ?? "");
    setValue(requirement
      ? requirement.value == null ? JSON.stringify(requirement.label) : JSON.stringify(requirement.value, null, 2)
      : JSON.stringify(initialValue));
    setUnit(requirement?.unit ?? "");
    setScopes(project.category ?? "");
    setAllCategories(false);
    setBaseSourceVersion(sourceVersion);
  }

  const staleSource = sourceVersion !== baseSourceVersion;

  const profile = useQuery({
    queryKey: ["shopping-profile"],
    queryFn: () => preferencesApi.profile(),
    retry: false,
  });
  const create = useMutation({
    mutationFn: async () => {
      if (!profile.data) throw new Error("Load your shopping profile before continuing.");
      let parsedValue: unknown;
      try {
        parsedValue = JSON.parse(value);
      } catch {
        throw new Error("Enter a valid JSON value, such as \"compact\" or 25.");
      }
      return preferencesApi.createCandidate(project.id, {
        expected_project_version: project.revision,
        expected_profile_version: profile.data.revision,
        ...(requirement
          ? { source_requirement_id: requirement.id }
          : { source_project_product_id: sourceProjectProductId! }),
        label: label.trim(),
        key: key.trim(),
        operator: operator || null,
        value: parsedValue,
        unit: unit.trim(),
        monetary,
        category_scopes: allCategories ? ["*"] : scopes.split(",").map((item) => item.trim()).filter(Boolean),
        rationale: initialRationale ?? "You selected this project preference for possible cross-project reuse.",
      });
    },
    onSuccess: async (result) => {
      setProblem("");
      setMessage(result.candidate.status === "pending" ? "Candidate saved for review in your profile." : "This candidate is already on your profile.");
      await queryClient.invalidateQueries({ queryKey: ["shopping-profile"] });
    },
    onError: async (error) => {
      setMessage("");
      setProblem(error instanceof Error ? error.message : "The candidate could not be saved.");
      if (error instanceof ApiRequestError && error.status === 409) {
        await Promise.all([
          queryClient.invalidateQueries({ queryKey: ["project", project.id] }),
          queryClient.invalidateQueries({ queryKey: ["shopping-profile"] }),
        ]);
      }
    },
  });

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setProblem("");
    setMessage("");
    create.mutate();
  }

  return (
    <details className="preference-promotion" key={sourceId}>
      <summary>Propose as a shopping preference</summary>
      {staleSource && <p className="field-error" role="alert">The project changed while this form was open. Review the current source before proposing it.</p>}
      {staleSource && <button className="button small-button quiet-button" type="button" onClick={reloadDraft}>Reload current source</button>}
      <p className="field-help">
        {requirement
          ? "This project preference stays local unless you review and accept it in your profile."
          : "This rejected-product judgment stays local unless you create a candidate and accept it in your profile."}
      </p>
      <form onSubmit={submit}>
        <label className="field-label" htmlFor={`profile-label-${sourceId}`}>Preference label</label>
        <input id={`profile-label-${sourceId}`} value={label} maxLength={300} required onChange={(event) => setLabel(event.target.value)} />

        <div className="field-grid">
          <div>
            <label className="field-label" htmlFor={`profile-key-${sourceId}`}>Preference key</label>
            <input id={`profile-key-${sourceId}`} value={key} maxLength={100} required onChange={(event) => setKey(event.target.value)} />
          </div>
          <div>
            <label className="field-label" htmlFor={`profile-operator-${sourceId}`}>Operator <span className="optional">Optional</span></label>
            <select id={`profile-operator-${sourceId}`} value={operator} onChange={(event) => setOperator(event.target.value as NonNullable<Requirement["operator"]> | "")}>
              <option value="">None</option>
              {(["eq", "gte", "lte", "contains", "one_of"] as const).map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
          </div>
        </div>

        <label className="field-label" htmlFor={`profile-value-${sourceId}`}>Value (JSON)</label>
        <textarea id={`profile-value-${sourceId}`} value={value} rows={2} required onChange={(event) => setValue(event.target.value)} />
        <label className="field-label" htmlFor={`profile-unit-${sourceId}`}>Unit or currency <span className="optional">Optional</span></label>
        <input id={`profile-unit-${sourceId}`} value={unit} maxLength={50} onChange={(event) => setUnit(event.target.value)} />

        <label className="field-label" htmlFor={`profile-scopes-${sourceId}`}>Categories</label>
        <input
          id={`profile-scopes-${sourceId}`}
          value={scopes}
          disabled={allCategories}
          required={!allCategories}
          placeholder="For example: furniture, office"
          onChange={(event) => setScopes(event.target.value)}
        />
        <label className="check-row">
          <input
            type="checkbox"
            checked={allCategories}
            disabled={monetary && !allCategories}
            onChange={(event) => setAllCategories(event.target.checked)}
          />
          <span>Apply across all categories</span>
        </label>
        <label className="check-row">
          <input type="checkbox" checked={monetary} onChange={(event) => {
            setMonetary(event.target.checked);
            if (event.target.checked) setAllCategories(false);
          }} />
          <span>This preference expresses an amount in a currency</span>
        </label>
        {monetary && <p className="field-help">Monetary preferences require a supported currency in Unit and a specific category.</p>}
        {profile.isError && <p className="field-error" role="alert">Shopping profile could not load. Close and reopen this form to retry.</p>}
        {problem && <p className="field-error" role="alert">{problem}</p>}
        {message && <p className="save-message" role="status">{message}</p>}
        <button className="button small-button secondary-button" type="submit" disabled={create.isPending || profile.isPending || profile.isError || staleSource || (monetary && allCategories)}>
          {create.isPending ? "Saving candidate…" : "Save candidate for review"}
        </button>
      </form>
    </details>
  );
}
