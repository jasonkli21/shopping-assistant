import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useState } from "react";
import { Link } from "react-router-dom";

import {
  ApiRequestError,
  CandidateRead,
  CatalogCorrectionCommand,
  CatalogCorrectionRevertCommand,
  catalogApi,
} from "../../api/client";

type NormalizeCommand = {
  request_key: string;
  expected_catalog_version: number;
  expected_project_version: number;
};
type RevertCommand = CatalogCorrectionRevertCommand;
type VariantChoice = {
  variant_id: string;
  product_id: string;
  canonical_name: string;
  brand: string | null;
  model_family: string | null;
  variant_name: string;
};
type StoredRecord = Record<string, unknown>;

function storageKey(projectId: string, candidateId: string, action: string) {
  return "shopping-assistant:catalog-command:" + projectId + ":" + candidateId + ":" + action;
}

function readStored<T>(key: string, isValid: (value: unknown) => value is T): T | null {
  try {
    const value = window.sessionStorage.getItem(key);
    if (!value) return null;
    const parsed: unknown = JSON.parse(value);
    if (isValid(parsed)) return parsed;
    window.sessionStorage.removeItem(key);
    return null;
  } catch {
    try {
      window.sessionStorage.removeItem(key);
    } catch {
      // Browser storage can be disabled; there is nothing to clean up.
    }
    return null;
  }
}

function writeStored<T>(key: string, value: T | null) {
  try {
    if (value) window.sessionStorage.setItem(key, JSON.stringify(value));
    else window.sessionStorage.removeItem(key);
  } catch {
    // Exact request recovery is best-effort when browser storage is unavailable.
  }
}

function requestKey(action: string) {
  return globalThis.crypto?.randomUUID?.() ?? action + "-" + Date.now() + "-" + Math.random().toString(16).slice(2);
}

function isKnownRejection(error: unknown) {
  return error instanceof ApiRequestError && [400, 404, 409, 422].includes(error.status);
}

function errorText(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback;
}

function choiceLabel(choice: VariantChoice) {
  return [choice.brand, choice.canonical_name, choice.model_family, choice.variant_name]
    .filter(Boolean)
    .join(" · ");
}

function validIdentityAttributes(value: unknown): Record<string, boolean | number | string> | undefined {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return undefined;
  const entries = Object.entries(value as Record<string, unknown>);
  if (entries.length > 12) return undefined;
  const allowedKeys = new Set(["bundle", "region", "color", "capacity", "generation", "condition", "size"]);
  if (entries.some(([key, item]) => !allowedKeys.has(key)
    || !["string", "number", "boolean"].includes(typeof item)
    || (typeof item === "number" && !Number.isFinite(item)))) {
    return undefined;
  }
  if (JSON.stringify(Object.fromEntries(entries)).length > 450) return undefined;
  return Object.fromEntries(entries) as Record<string, boolean | number | string>;
}

function isRecord(value: unknown): value is StoredRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function hasCommandVersions(value: unknown): value is StoredRecord & {
  request_key: string;
  expected_catalog_version: number;
  expected_project_version: number;
} {
  return isRecord(value)
    && typeof value.request_key === "string"
    && value.request_key.length >= 8
    && value.request_key.length <= 100
    && Number.isInteger(value.expected_catalog_version)
    && Number(value.expected_catalog_version) >= 1
    && Number.isInteger(value.expected_project_version)
    && Number(value.expected_project_version) >= 1;
}

function isNormalizeCommand(value: unknown): value is NormalizeCommand {
  return hasCommandVersions(value);
}

function isRevertCommand(value: unknown): value is RevertCommand {
  return hasCommandVersions(value);
}

function isCorrectionCommand(value: unknown): value is CatalogCorrectionCommand {
  if (!hasCommandVersions(value) || typeof value.reason !== "string" || value.reason.length < 3 || value.reason.length > 500) return false;
  const targets = [value.target_variant_id, value.new_variant, value.new_product].filter((target) => target !== undefined && target !== null);
  if (targets.length !== 1) return false;
  if (value.target_variant_id !== undefined && value.target_variant_id !== null) {
    return typeof value.target_variant_id === "string";
  }
  if (value.new_variant !== undefined && value.new_variant !== null) {
    const target = value.new_variant;
    return isRecord(target)
      && typeof target.product_id === "string"
      && typeof target.display_name === "string"
      && validIdentityAttributes(target.identity_attributes) !== undefined
      && Array.isArray(target.category_attributes);
  }
  const target = value.new_product;
  return isRecord(target)
    && typeof target.canonical_name === "string"
    && typeof target.variant_name === "string"
    && validIdentityAttributes(target.identity_attributes) !== undefined
    && Array.isArray(target.category_attributes);
}

export function CatalogCandidateActions({
  projectId,
  candidate,
  projectVersion,
  catalogVersion,
}: {
  projectId: string;
  candidate: CandidateRead;
  projectVersion: number;
  catalogVersion?: number;
}) {
  const queryClient = useQueryClient();
  const normalizeKey = storageKey(projectId, candidate.id, "normalize");
  const correctionKey = storageKey(projectId, candidate.id, "correction");
  const revertKey = storageKey(projectId, candidate.id, "revert");
  const [pendingNormalize, setPendingNormalize] = useState<NormalizeCommand | null>(() =>
    readStored(normalizeKey, isNormalizeCommand),
  );
  const [pendingCorrection, setPendingCorrection] = useState<CatalogCorrectionCommand | null>(() =>
    readStored(correctionKey, isCorrectionCommand),
  );
  const [pendingRevert, setPendingRevert] = useState<RevertCommand | null>(() =>
    readStored(revertKey, isRevertCommand),
  );
  const [normalizationError, setNormalizationError] = useState("");
  const [correctionError, setCorrectionError] = useState("");
  const [correctionOpen, setCorrectionOpen] = useState(false);
  const [searchText, setSearchText] = useState("");
  const [selectedVariantId, setSelectedVariantId] = useState("");
  const [selectedProductId, setSelectedProductId] = useState("");
  const [correctionReason, setCorrectionReason] = useState("");
  const [newProductMode, setNewProductMode] = useState(false);
  const [newVariantMode, setNewVariantMode] = useState(false);
  const [newProductName, setNewProductName] = useState("");
  const [newBrand, setNewBrand] = useState("");
  const [newCategory, setNewCategory] = useState("");
  const [newModel, setNewModel] = useState("");
  const [newVariantName, setNewVariantName] = useState("");
  const [newIdentityJson, setNewIdentityJson] = useState("{}");
  const mapping = candidate.normalization;
  const variantsQuery = useQuery({
    queryKey: ["catalog-variants", searchText],
    queryFn: ({ signal }) => catalogApi.listVariants(searchText, 20, undefined, signal),
    enabled: correctionOpen && (!newProductMode || newVariantMode),
    retry: false,
    refetchOnWindowFocus: false,
  });
  const refreshCatalog = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["project", projectId] }),
      queryClient.invalidateQueries({ queryKey: ["project-products", projectId] }),
      queryClient.invalidateQueries({ queryKey: ["catalog-variants"] }),
      queryClient.invalidateQueries({ queryKey: ["discovery-candidates", projectId] }),
    ]);
  };

  const normalize = useMutation({
    mutationFn: (command: NormalizeCommand) =>
      catalogApi.normalizeCandidate(projectId, candidate.id, command),
    onSuccess: async (result) => {
      setPendingNormalize(null);
      writeStored(normalizeKey, null);
      setNormalizationError(
        result.status === "auto_linked"
          ? "Product details were saved."
          : result.status === "unresolved"
            ? "This candidate needs a manual match: " + result.reason.replaceAll("_", " ") + "."
            : "Page retrieval " + result.status + ": " + (result.failure_code?.replaceAll("_", " ") ?? "no product details found") + ".",
      );
      await refreshCatalog();
    },
    onError: async (error) => {
      setNormalizationError(errorText(error, "Normalization could not finish."));
      if (isKnownRejection(error)) {
        setPendingNormalize(null);
        writeStored(normalizeKey, null);
      }
      if (error instanceof ApiRequestError && error.status === 409) await refreshCatalog();
    },
  });

  const correct = useMutation({
    mutationFn: (command: CatalogCorrectionCommand) =>
      catalogApi.correctCandidate(projectId, candidate.id, command),
    onSuccess: async () => {
      setPendingCorrection(null);
      writeStored(correctionKey, null);
      setCorrectionError("Your assignment was saved and can be reverted.");
      setCorrectionOpen(false);
      await refreshCatalog();
    },
    onError: async (error) => {
      setCorrectionError(errorText(error, "Your correction could not be saved."));
      if (isKnownRejection(error)) {
        setPendingCorrection(null);
        writeStored(correctionKey, null);
      }
      if (error instanceof ApiRequestError && error.status === 409) await refreshCatalog();
    },
  });

  const revert = useMutation({
    mutationFn: (command: RevertCommand) =>
      catalogApi.revertCandidateCorrection(projectId, candidate.id, command),
    onSuccess: async () => {
      setPendingRevert(null);
      writeStored(revertKey, null);
      setCorrectionError("Your previous mapping was restored.");
      await refreshCatalog();
    },
    onError: async (error) => {
      setCorrectionError(errorText(error, "The correction could not be reverted."));
      if (isKnownRejection(error)) {
        setPendingRevert(null);
        writeStored(revertKey, null);
      }
      if (error instanceof ApiRequestError && error.status === 409) await refreshCatalog();
    },
  });

  function submitNormalization() {
    if (!catalogVersion) {
      setNormalizationError("Load the current catalog version before normalizing.");
      return;
    }
    const command = pendingNormalize ?? {
      request_key: requestKey("catalog-normalize"),
      expected_catalog_version: catalogVersion,
      expected_project_version: projectVersion,
    };
    setPendingNormalize(command);
    writeStored(normalizeKey, command);
    setNormalizationError("");
    normalize.mutate(command);
  }

  function submitCorrection(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!catalogVersion) {
      setCorrectionError("Load the current catalog version before saving a correction.");
      return;
    }
    if (!correctionReason.trim()) {
      setCorrectionError("Add a short reason for this correction.");
      return;
    }
    let command: CatalogCorrectionCommand;
    if (newProductMode) {
      let identityAttributes: Record<string, boolean | number | string> | undefined;
      try {
        identityAttributes = validIdentityAttributes(JSON.parse(newIdentityJson));
      } catch {
        identityAttributes = undefined;
      }
      if (!identityAttributes) {
        setCorrectionError("Variant identity must be a JSON object with up to 12 text, number, or boolean values.");
        return;
      }
      command = {
        request_key: requestKey("catalog-correction"),
        expected_catalog_version: catalogVersion,
        expected_project_version: projectVersion,
        reason: correctionReason.trim(),
        new_product: {
          canonical_name: newProductName.trim(),
          brand: newBrand.trim() || null,
          category: newCategory.trim() || null,
          model_family: newModel.trim() || null,
          variant_name: newVariantName.trim() || "Unspecified",
          identity_attributes: identityAttributes,
          category_attributes: [],
        },
      };
    } else if (newVariantMode) {
      let identityAttributes: Record<string, boolean | number | string> | undefined;
      try {
        identityAttributes = validIdentityAttributes(JSON.parse(newIdentityJson));
      } catch {
        identityAttributes = undefined;
      }
      if (!selectedProductId) {
        setCorrectionError("Choose the product family for this new variant.");
        return;
      }
      if (!identityAttributes) {
        setCorrectionError("Variant identity must be a JSON object with up to 12 text, number, or boolean values.");
        return;
      }
      command = {
        request_key: requestKey("catalog-correction"),
        expected_catalog_version: catalogVersion,
        expected_project_version: projectVersion,
        reason: correctionReason.trim(),
        new_variant: {
          product_id: selectedProductId,
          display_name: newVariantName.trim() || "Unspecified",
          identity_attributes: identityAttributes,
          category_attributes: [],
        },
      };
    } else {
      if (!selectedVariantId) {
        setCorrectionError("Choose a product variant or create a new product.");
        return;
      }
      command = {
        request_key: requestKey("catalog-correction"),
        expected_catalog_version: catalogVersion,
        expected_project_version: projectVersion,
        reason: correctionReason.trim(),
        target_variant_id: selectedVariantId,
      };
    }
    setPendingCorrection(command);
    writeStored(correctionKey, command);
    setCorrectionError("");
    correct.mutate(command);
  }

  function replayCorrection() {
    if (pendingCorrection) correct.mutate(pendingCorrection);
  }

  function submitRevert() {
    if (!catalogVersion) {
      setCorrectionError("Load the current catalog version before reverting.");
      return;
    }
    const command = pendingRevert ?? {
      request_key: requestKey("catalog-revert"),
      expected_catalog_version: catalogVersion,
      expected_project_version: projectVersion,
    };
    setPendingRevert(command);
    writeStored(revertKey, command);
    revert.mutate(command);
  }

  return (
    <div className="catalog-candidate-actions">
      {mapping?.project_product_id && mapping.product_id ? (
        <div className="normalized-product-link">
          <span className="catalog-status-pill">{mapping.status === "manual_linked" || mapping.can_revert_correction || mapping.reason === "manual_mapping_preserved" ? "Manual match" : "Normalized"}</span>
          <Link to={"/products/" + mapping.product_id}>View product details</Link>
          {mapping.reason && <small>{mapping.reason.replaceAll("_", " ")}</small>}
        </div>
      ) : (
        <p className="catalog-status-pill unresolved-pill">
          {mapping?.latest_observation_status === "failed" || mapping?.latest_observation_status === "blocked" || mapping?.latest_observation_status === "unsupported"
            ? "Page " + mapping.latest_observation_status
            : mapping?.status === "unresolved" ? "Needs a product match" : "Provisional candidate"}
        </p>
      )}

      <div className="catalog-action-row">
        <button className="button secondary-button" type="button" onClick={submitNormalization} disabled={normalize.isPending || !catalogVersion}>
          {normalize.isPending ? "Reading product page…" : pendingNormalize ? "Retry the same normalization" : mapping?.latest_observation_status && mapping.latest_observation_status !== "succeeded" ? "Retry page retrieval" : "Normalize product page"}
        </button>
        <button className="button quiet-button" type="button" onClick={() => setCorrectionOpen((value) => !value)}>
          {correctionOpen ? "Close correction" : "Assign or correct match"}
        </button>
        {mapping?.can_revert_correction && (
          <button className="button quiet-button" type="button" onClick={submitRevert} disabled={revert.isPending || !catalogVersion}>
            {revert.isPending ? "Reverting correction…" : pendingRevert ? "Retry revert" : "Revert latest correction"}
          </button>
        )}
      </div>
      {normalize.isPending && <p className="catalog-action-status" role="status">Retrieval and extraction are running. This page can stay open while they finish.</p>}
      {normalizationError && <p className={normalize.isError ? "field-error" : "catalog-action-status"} role={normalize.isError ? "alert" : "status"}>{normalizationError}</p>}
      {correctionError && <p className={correct.isError || revert.isError ? "field-error" : "catalog-action-status"} role={correct.isError || revert.isError ? "alert" : "status"}>{correctionError}</p>}

      {correctionOpen && (
        <form className="catalog-correction-form" onSubmit={submitCorrection}>
          <div className="catalog-correction-mode">
            <label>
              <input type="radio" checked={!newProductMode && !newVariantMode} onChange={() => { setNewProductMode(false); setNewVariantMode(false); }} />
              <span>Assign to an existing variant</span>
            </label>
            <label>
              <input type="radio" checked={newVariantMode} onChange={() => { setNewProductMode(false); setNewVariantMode(true); }} />
              <span>Create a new variant under an existing product</span>
            </label>
            <label>
              <input type="radio" checked={newProductMode} onChange={() => { setNewProductMode(true); setNewVariantMode(false); }} />
              <span>Create a new product and variant</span>
            </label>
          </div>
          {!newProductMode ? (
            <>
              <label className="field-label" htmlFor={"variant-search-" + candidate.id}>Find an existing variant</label>
              <input
                id={"variant-search-" + candidate.id}
                value={searchText}
                onChange={(event) => setSearchText(event.target.value)}
                placeholder="Search product, brand, or model"
              />
              {variantsQuery.isPending && <p role="status">Loading catalog variants…</p>}
              {variantsQuery.isError && <p role="alert">{errorText(variantsQuery.error, "Catalog variants could not load.")}</p>}
              {variantsQuery.data?.items.length && !newVariantMode ? (
                <label className="field-label" htmlFor={"variant-choice-" + candidate.id}>
                  Product variant
                  <select
                    id={"variant-choice-" + candidate.id}
                    value={selectedVariantId}
                    onChange={(event) => setSelectedVariantId(event.target.value)}
                  >
                    <option value="">Choose a variant</option>
                    {variantsQuery.data.items.map((choice) => (
                      <option key={choice.variant_id} value={choice.variant_id}>{choiceLabel(choice)}</option>
                    ))}
                  </select>
                </label>
              ) : !variantsQuery.data?.items.length && !variantsQuery.isPending && !variantsQuery.isError ? (
                <p className="quiet-state">No matching variants yet. Create a product below.</p>
              ) : null}
              {newVariantMode && variantsQuery.data?.items.length ? (
                <>
                  <label className="field-label" htmlFor={"product-choice-" + candidate.id}>
                    Product family
                    <select
                      id={"product-choice-" + candidate.id}
                      value={selectedProductId}
                      onChange={(event) => setSelectedProductId(event.target.value)}
                    >
                      <option value="">Choose a product</option>
                      {[...new Map(variantsQuery.data.items.map((choice) => [choice.product_id, choice])).values()].map((choice) => (
                        <option key={choice.product_id} value={choice.product_id}>{[choice.brand, choice.canonical_name, choice.model_family].filter(Boolean).join(" · ")}</option>
                      ))}
                    </select>
                  </label>
                  <label className="field-label" htmlFor={"new-variant-name-" + candidate.id}>Variant name</label>
                  <input id={"new-variant-name-" + candidate.id} value={newVariantName} onChange={(event) => setNewVariantName(event.target.value)} maxLength={300} placeholder="Describe this variant" />
                  <label className="field-label" htmlFor={"identity-json-" + candidate.id}>Known variant identity values <span className="optional">JSON, for example bundle and region values</span></label>
                  <textarea id={"identity-json-" + candidate.id} value={newIdentityJson} onChange={(event) => setNewIdentityJson(event.target.value)} rows={3} />
                </>
              ) : null}
            </>
          ) : (
            <>
              <label className="field-label" htmlFor={"new-product-name-" + candidate.id}>Canonical product name</label>
              <input id={"new-product-name-" + candidate.id} value={newProductName} onChange={(event) => setNewProductName(event.target.value)} maxLength={300} required />
              <div className="catalog-correction-fields">
                <label><span className="field-label">Brand <span className="optional">Optional</span></span><input value={newBrand} onChange={(event) => setNewBrand(event.target.value)} maxLength={200} /></label>
                <label><span className="field-label">Category <span className="optional">Optional</span></span><input value={newCategory} onChange={(event) => setNewCategory(event.target.value)} maxLength={100} /></label>
                <label><span className="field-label">Model family <span className="optional">Optional</span></span><input value={newModel} onChange={(event) => setNewModel(event.target.value)} maxLength={200} /></label>
                <label><span className="field-label">Variant name</span><input value={newVariantName} onChange={(event) => setNewVariantName(event.target.value)} maxLength={300} placeholder="Unspecified" /></label>
              </div>
              <label className="field-label" htmlFor={"identity-json-" + candidate.id}>Known variant identity values <span className="optional">JSON, for example a bundle value</span></label>
              <textarea id={"identity-json-" + candidate.id} value={newIdentityJson} onChange={(event) => setNewIdentityJson(event.target.value)} rows={3} />
            </>
          )}
          <label className="field-label" htmlFor={"correction-reason-" + candidate.id}>Why is this match correct?</label>
          <textarea id={"correction-reason-" + candidate.id} value={correctionReason} onChange={(event) => setCorrectionReason(event.target.value)} rows={2} maxLength={500} minLength={3} required />
          {correctionError && <p className="field-error" role="alert">{correctionError}</p>}
          {pendingCorrection ? (
            <div className="saved-command-notice" role="status">
              <p>This correction may already have been saved.</p>
              <button className="button secondary-button" type="button" disabled={correct.isPending} onClick={replayCorrection}>
                {correct.isPending ? "Checking correction…" : "Retry the same correction"}
              </button>
            </div>
          ) : (
            <button className="button primary-button" type="submit" disabled={correct.isPending || !catalogVersion}>
              {correct.isPending ? "Saving correction…" : "Save manual correction"}
            </button>
          )}
          <p className="field-help">Your choice is recorded with a reason and can be reverted. Offers stay attached to the variant where they were observed.</p>
        </form>
      )}
    </div>
  );
}
