import { FormEvent, useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";

import {
  ApiRequestError,
  ComparisonCreate,
  ComparisonDimension,
  ComparisonPatch,
  ComparisonRead,
  ProjectProductPage,
  comparisonsApi,
  catalogApi,
  projectsApi,
} from "../../api/client";
import { ProjectAssistant } from "../assistant/ProjectAssistant";
import { ProjectNavigation } from "../projects/ProjectNavigation";

const DEFAULT_DIMENSION: ComparisonDimension = {
  key: "price",
  label: "Latest offer",
  dimension_type: "offer",
};

function readableError(error: unknown) {
  return error instanceof Error ? error.message : "The comparison could not be saved.";
}

function productHref(projectId: string, comparison: ComparisonRead, projectProductId: string) {
  const product = comparison.products.find((item) => item.project_product_id === projectProductId);
  if (!product) return undefined;
  return `/products/${product.product_id}?${new URLSearchParams({
    variant: product.variant_id,
    project: projectId,
    project_product: product.project_product_id,
  }).toString()}`;
}

function displayCell(value: unknown, unit?: string | null) {
  if (value === null || value === undefined || value === "") return "Unknown";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return `${value}${unit ? ` ${unit}` : ""}`;
  }
  if (Array.isArray(value)) return `${value.length} evidence ${value.length === 1 ? "claim" : "claims"}`;
  if (typeof value === "object") {
    const item = value as Record<string, unknown>;
    if (typeof item.amount === "string" || item.amount === null) {
      return item.amount && item.currency ? `${item.currency} ${item.amount}` : "Price unknown";
    }
    if (typeof item.status === "string") return item.status.replaceAll("_", " ");
  }
  return "Available in source details";
}

function statusLabel(status: string) {
  switch (status) {
    case "known": return "Known";
    case "unknown": return "Unknown";
    case "conflict": return "Conflicting evidence";
    case "stale": return "Stale context";
    case "incomparable": return "Not comparable";
    default: return status;
  }
}

export function ComparisonPage() {
  const { projectId, comparisonId } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [dimensions, setDimensions] = useState<ComparisonDimension[]>([DEFAULT_DIMENSION]);
  const [dimensionType, setDimensionType] = useState<ComparisonDimension["dimension_type"]>("fact");
  const [dimensionKey, setDimensionKey] = useState("");
  const [dimensionLabel, setDimensionLabel] = useState("");
  const [dimensionUnit, setDimensionUnit] = useState("");
  const [title, setTitle] = useState("Product comparison");
  const [error, setError] = useState("");

  const projectQuery = useQuery({
    queryKey: ["project", projectId],
    queryFn: ({ signal }) => projectsApi.get(projectId!, signal),
    enabled: Boolean(projectId),
    retry: false,
  });
  const productsQuery = useQuery({
    queryKey: ["project-products", projectId],
    queryFn: ({ signal }) => catalogApi.listProjectProducts(projectId!, 100, undefined, signal),
    enabled: Boolean(projectId && projectQuery.data),
    retry: false,
  });
  const comparisonsQuery = useQuery({
    queryKey: ["project-comparisons", projectId],
    queryFn: ({ signal }) => comparisonsApi.list(projectId!, 50, undefined, signal),
    enabled: Boolean(projectId && projectQuery.data),
    retry: false,
  });
  const comparisonQuery = useQuery({
    queryKey: ["comparison", projectId, comparisonId],
    queryFn: ({ signal }) => comparisonsApi.get(projectId!, comparisonId!, signal),
    enabled: Boolean(projectId && comparisonId),
    retry: false,
  });
  const project = projectQuery.data;
  const productPage = productsQuery.data as ProjectProductPage | undefined;
  const products = productPage?.items ?? [];
  const currentComparison = comparisonQuery.data;

  useEffect(() => {
    if (!currentComparison) return;
    setTitle(currentComparison.title);
    setSelectedIds(currentComparison.products.map((item) => item.project_product_id));
    setDimensions((current) => currentComparison.dimensions.length > 0
      ? currentComparison.dimensions.map(({ key, label, unit, dimension_type }) => ({ key, label, unit, dimension_type }))
      : current);
  }, [currentComparison]);

  const create = useMutation({
    mutationFn: () => {
      const command: ComparisonCreate = {
        expected_version: project!.revision,
        title: title.trim() || "Product comparison",
        project_product_ids: selectedIds,
        dimensions,
        display_mode: "all",
      };
      return comparisonsApi.create(projectId!, command);
    },
    onSuccess: async (comparison) => {
      setError("");
      queryClient.setQueryData(["comparison", projectId, comparison.id], comparison);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["project", projectId] }),
        queryClient.invalidateQueries({ queryKey: ["project-comparisons", projectId] }),
      ]);
      navigate(`/projects/${projectId}/compare/${comparison.id}`);
    },
    onError: (caught) => {
      setError(readableError(caught));
      if (caught instanceof ApiRequestError && caught.status === 409) {
        void queryClient.invalidateQueries({ queryKey: ["project", projectId] });
      }
    },
  });
  const update = useMutation({
    mutationFn: (command: ComparisonPatch) => comparisonsApi.update(projectId!, comparisonId!, command),
    onSuccess: async (comparison) => {
      queryClient.setQueryData(["comparison", projectId, comparisonId], comparison);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["project", projectId] }),
        queryClient.invalidateQueries({ queryKey: ["project-comparisons", projectId] }),
      ]);
      setError("");
    },
    onError: (caught) => {
      setError(readableError(caught));
      if (caught instanceof ApiRequestError && caught.status === 409) {
        void queryClient.invalidateQueries({ queryKey: ["project", projectId] });
        void queryClient.invalidateQueries({ queryKey: ["comparison", projectId, comparisonId] });
      }
    },
  });
  const regenerate = useMutation({
    mutationFn: () => comparisonsApi.regenerate(
      projectId!, comparisonId!, project!.revision, currentComparison!.comparison_revision,
    ),
    onSuccess: async (comparison) => {
      queryClient.setQueryData(["comparison", projectId, comparisonId], comparison);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["project", projectId] }),
        queryClient.invalidateQueries({ queryKey: ["project-comparisons", projectId] }),
      ]);
      setError("");
    },
    onError: (caught) => setError(readableError(caught)),
  });
  const remove = useMutation({
    mutationFn: () => comparisonsApi.delete(
      projectId!, comparisonId!, project!.revision, currentComparison!.comparison_revision,
    ),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["project", projectId] }),
        queryClient.invalidateQueries({ queryKey: ["project-comparisons", projectId] }),
      ]);
      navigate(`/projects/${projectId}/compare`);
    },
    onError: (caught) => setError(readableError(caught)),
  });

  const usedKeys = useMemo(() => new Set(dimensions.map((item) => item.key)), [dimensions]);

  function addDimension(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const key = dimensionKey.trim();
    const label = dimensionLabel.trim();
    if (!key || !label || usedKeys.has(key) || dimensions.length >= 20) return;
    setDimensions((current) => [...current, {
      key,
      label,
      dimension_type: dimensionType,
      ...(dimensionUnit.trim() ? { unit: dimensionUnit.trim() } : {}),
    }]);
    setDimensionKey("");
    setDimensionLabel("");
    setDimensionUnit("");
  }

  function updateComparison(patch: Omit<ComparisonPatch, "expected_version" | "expected_comparison_version">) {
    if (!project || !currentComparison) return;
    update.mutate({
      expected_version: project.revision,
      expected_comparison_version: currentComparison.comparison_revision,
      ...patch,
    });
  }

  if (!projectId) return null;
  if (projectQuery.isPending) return <main className="shell loading-page"><p role="status">Loading project…</p></main>;
  if (projectQuery.isError || !project) {
    return <main className="shell state-page"><h1>Comparison could not load.</h1><p role="alert">{readableError(projectQuery.error)}</p><Link to="/">Return to projects</Link></main>;
  }

  const selectedComparison = comparisonId ? currentComparison : undefined;
  return (
    <main className="shell comparison-workspace-shell">
      <header className="app-header">
        <Link className="brand" to="/" aria-label="Shopping Assistant home"><span className="brand-mark" aria-hidden="true">S</span><span>Shopping Assistant</span></Link>
        <Link className="header-back" to={`/projects/${project.id}`}>Project overview</Link>
      </header>
      <nav aria-label="Breadcrumb" className="breadcrumbs"><Link to="/">Projects</Link><span aria-hidden="true">/</span><Link to={`/projects/${project.id}`}>{project.title}</Link><span aria-hidden="true">/</span><span>Compare</span></nav>
      <ProjectNavigation projectId={project.id} />
      <section className="workspace-title-row">
        <div><p className="eyebrow">Saved comparison · Project revision {project.revision}</p><h1 tabIndex={-1}>Compare variants</h1><p className="overview-lede">Compare exact project variants using current catalog facts and cited evidence. Unknowns stay visible.</p></div>
      </section>

      {!comparisonId && (
        <section className="card comparison-builder" aria-labelledby="comparison-builder-title">
          <div className="section-heading"><div><p className="eyebrow">New saved view</p><h2 id="comparison-builder-title">Choose variants and dimensions</h2></div></div>
          {productsQuery.isPending && <p role="status">Loading project variants…</p>}
          {productsQuery.isError && <div className="notice error-notice"><p role="alert">{readableError(productsQuery.error)}</p><button className="button quiet-button" type="button" onClick={() => void productsQuery.refetch()}>Retry products</button></div>}
          {!productsQuery.isPending && !productsQuery.isError && products.length < 2 && (
            <div className="empty-state"><h3>Two project variants are needed.</h3><p>Find products in Discover, then normalize at least two exact variants into this project.</p><Link className="button secondary-button" to={`/projects/${project.id}/discover`}>Go to Discover</Link></div>
          )}
          {products.length >= 2 && (
            <>
              <label className="field-label comparison-title-field">Comparison title<input value={title} maxLength={160} onChange={(event) => setTitle(event.target.value)} /></label>
              <fieldset className="comparison-product-picker">
                <legend>Choose 2 to 6 exact variants</legend>
                {products.map((item) => (
                  <label className="comparison-product-choice" key={item.id}>
                    <input
                      type="checkbox"
                      checked={selectedIds.includes(item.id)}
                      disabled={!selectedIds.includes(item.id) && selectedIds.length >= 6}
                      onChange={(event) => setSelectedIds((current) => event.target.checked
                        ? [...current, item.id]
                        : current.filter((id) => id !== item.id))}
                    />
                    <span><strong>{item.canonical_name}</strong><small>{[item.brand, item.variant_name].filter(Boolean).join(" · ")}</small></span>
                  </label>
                ))}
              </fieldset>
              <ul className="dimension-chip-list" aria-label="Selected comparison dimensions">
                {dimensions.map((dimension) => <li key={dimension.key}><span>{dimension.label} · {dimension.dimension_type.replaceAll("_", " ")}</span><button type="button" aria-label={`Remove ${dimension.label} dimension`} onClick={() => setDimensions((current) => current.filter((item) => item.key !== dimension.key))}>×</button></li>)}
              </ul>
              <form className="comparison-dimension-form" onSubmit={addDimension}>
                <label className="field-label">Type<select value={dimensionType} onChange={(event) => setDimensionType(event.target.value as ComparisonDimension["dimension_type"])}><option value="fact">Catalog fact</option><option value="offer">Offer observation</option><option value="evidence">Evidence claim</option><option value="project_fit">Requirement fit</option><option value="user_note">User note</option></select></label>
                {dimensionType === "project_fit" ? (
                  <label className="field-label">Requirement<select value={dimensionKey} onChange={(event) => { const req = project.requirements.find((item) => item.id === event.target.value); setDimensionKey(event.target.value); setDimensionLabel(req?.label ?? ""); }}><option value="">Choose a requirement</option>{project.requirements.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select></label>
                ) : (
                  <label className="field-label">Attribute key<input value={dimensionKey} maxLength={100} placeholder={dimensionType === "evidence" ? "warranty" : "battery_runtime"} onChange={(event) => setDimensionKey(event.target.value)} /></label>
                )}
                <label className="field-label">Display label<input value={dimensionLabel} maxLength={100} placeholder="Warranty" onChange={(event) => setDimensionLabel(event.target.value)} /></label>
                <label className="field-label">Unit (optional)<input value={dimensionUnit} maxLength={30} onChange={(event) => setDimensionUnit(event.target.value)} /></label>
                <button className="button quiet-button" type="submit" disabled={!dimensionKey.trim() || !dimensionLabel.trim() || usedKeys.has(dimensionKey.trim()) || dimensions.length >= 20}>Add dimension</button>
              </form>
              <button className="button primary-button" type="button" disabled={create.isPending || selectedIds.length < 2 || selectedIds.length > 6 || dimensions.length < 1} onClick={() => create.mutate()}>{create.isPending ? "Saving comparison…" : "Save comparison"}</button>
            </>
          )}
          {error && <p className="field-error" role="alert">{error}</p>}
        </section>
      )}

      {comparisonId && (
        <section className="card comparison-view-card" aria-labelledby="saved-comparison-title">
          {comparisonQuery.isPending && <p role="status">Loading saved comparison…</p>}
          {comparisonQuery.isError && <div className="notice error-notice"><p role="alert">{readableError(comparisonQuery.error)}</p><button className="button quiet-button" type="button" onClick={() => void comparisonQuery.refetch()}>Retry comparison</button></div>}
          {selectedComparison && (
            <>
              <div className="comparison-view-heading">
                <div><p className="eyebrow">Snapshot {selectedComparison.snapshot_id.slice(0, 8)} · generated {new Date(selectedComparison.generated_at).toLocaleString()}</p><h2 id="saved-comparison-title">{selectedComparison.title}</h2><p>Comparison revision {selectedComparison.comparison_revision} · captured at project revision {selectedComparison.project_revision}</p></div>
                <div className="comparison-view-actions">
                  <button className="button secondary-button" type="button" disabled={update.isPending} onClick={() => updateComparison({ display_mode: selectedComparison.display_mode === "all" ? "differences" : "all" })}>{selectedComparison.display_mode === "all" ? "Show differences only" : "Show all dimensions"}</button>
                  <button className="button quiet-button" type="button" disabled={regenerate.isPending || !selectedComparison.stale} onClick={() => regenerate.mutate()}>{regenerate.isPending ? "Regenerating…" : "Regenerate snapshot"}</button>
                  <button className="button quiet-button" type="button" disabled={remove.isPending} onClick={() => { if (window.confirm("Delete this saved comparison?")) remove.mutate(); }}>{remove.isPending ? "Deleting…" : "Delete comparison"}</button>
                </div>
              </div>
              {selectedComparison.stale && <div className="notice stale-comparison-notice"><strong>This comparison is stale.</strong><span>Project requirements, saved decisions, catalog offers, product facts, notes, or evidence changed after this snapshot. Regenerate to create a new saved version.</span></div>}
              {selectedComparison.display_mode === "differences" && (selectedComparison.hidden_equal_dimensions ?? 0) > 0 && <p className="quiet-state">{selectedComparison.hidden_equal_dimensions} dimension{selectedComparison.hidden_equal_dimensions === 1 ? "" : "s"} with equally known values hidden.</p>}
              {selectedComparison.dimensions.length === 0 ? (
                <div className="empty-state compact-empty"><h3>No meaningful differences are established.</h3><p>Unknowns and conflicts are never hidden. Switch to all dimensions to inspect the complete saved view.</p></div>
              ) : (
                <div className="comparison-table-scroll" role="region" aria-label="Product comparison table" tabIndex={0}>
                  <table className="comparison-table">
                    <caption>Comparison of exact product variants. Offer observation dates are shown with prices.</caption>
                    <thead><tr><th scope="col">Dimension</th>{selectedComparison.products.map((item) => <th scope="col" key={item.project_product_id}><Link to={productHref(project.id, selectedComparison, item.project_product_id) ?? "#"}>{item.canonical_name}</Link><small>{item.variant_name}</small>{Object.keys(item.identity_attributes).length > 0 && <small>{Object.entries(item.identity_attributes).map(([key, value]) => `${key}: ${typeof value === "object" && value !== null && "value" in value ? String((value as { value: unknown }).value) : String(value)}`).join(" · ")}</small>}</th>)}</tr></thead>
                    <tbody>
                      {selectedComparison.dimensions.map((dimension) => (
                        <tr key={dimension.key}>
                          <th scope="row"><strong>{dimension.label}</strong><small>{dimension.dimension_type.replaceAll("_", " ")}{dimension.unit ? ` · ${dimension.unit}` : ""}</small></th>
                          {dimension.cells.map((cell) => (
                            <td key={cell.project_product_id}>
                              <span className={`comparison-cell-status cell-${cell.status}`}>{statusLabel(cell.status)}</span>
                              {dimension.dimension_type === "evidence" && Array.isArray(cell.value) ? (
                                <ul className="comparison-evidence-list">
                                  {(cell.value as Array<Record<string, unknown>>).map((claim) => (
                                    <li key={String(claim.claim_id)}>
                                      <p>{String(claim.assertion ?? "Claim text unavailable")}</p>
                                      <small>{String(claim.source_title ?? "Source title unknown")} · {String(claim.freshness ?? "freshness unknown")}</small>
                                      {typeof claim.source_url === "string" && <a href={claim.source_url} target="_blank" rel="noopener noreferrer">Open source<span className="sr-only"> (opens in a new tab)</span></a>}
                                      <small>Claim {String(claim.claim_id).slice(0, 8)} · snapshot {String(claim.snapshot_id).slice(0, 8)}</small>
                                    </li>
                                  ))}
                                </ul>
                              ) : (
                                <p className="comparison-cell-value">{displayCell(cell.value, cell.unit)}</p>
                              )}
                              {dimension.dimension_type === "offer" && typeof cell.value === "object" && cell.value !== null && (
                                <small className="comparison-offer-meta">{String((cell.value as Record<string, unknown>).retailer ?? "Retailer unknown")} · observed {new Date(String((cell.value as Record<string, unknown>).observed_at)).toLocaleString()}</small>
                              )}
                              {dimension.dimension_type === "project_fit" && typeof cell.value === "object" && cell.value !== null && <p>{String((cell.value as Record<string, unknown>).rationale ?? "Fit rationale is unknown.")}</p>}
                              {dimension.dimension_type === "project_fit" && Array.isArray(cell.provenance?.claim_ids) && cell.provenance.claim_ids.length > 0 && <Link className="comparison-inspect-link" to={productHref(project.id, selectedComparison, cell.project_product_id) ?? "#"}>Inspect cited evidence ({cell.provenance.claim_ids.length})</Link>}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              {error && <p className="field-error" role="alert">{error}</p>}
            </>
          )}
        </section>
      )}

      {comparisonsQuery.data?.items.length ? (
        <section className="card saved-comparison-list" aria-labelledby="saved-comparisons-heading">
          <div className="section-heading"><div><p className="eyebrow">Persisted project views</p><h2 id="saved-comparisons-heading">Saved comparisons</h2></div></div>
          <ul>{comparisonsQuery.data.items.map((item) => <li key={item.id}><Link to={`/projects/${project.id}/compare/${item.id}`}>{item.title}</Link><span>{item.products.length} variants · {item.stale ? "stale" : "current"}</span></li>)}</ul>
        </section>
      ) : null}
      {comparisonsQuery.isError && <p className="field-error" role="alert">Saved comparisons could not load: {readableError(comparisonsQuery.error)}</p>}
      <ProjectAssistant project={project} />
    </main>
  );
}
