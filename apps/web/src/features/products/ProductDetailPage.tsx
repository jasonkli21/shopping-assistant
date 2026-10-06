import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { useEffect, useMemo } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";

import { ApiRequestError, ProductRead, catalogApi, projectsApi } from "../../api/client";
import { ProductResearch } from "./ProductResearch";
import { ProjectNavigation } from "../projects/ProjectNavigation";
import { FavoriteButton } from "./FavoriteButton";
import { ProductDecisionActions } from "../decisions/ProductDecisionActions";
import { UserNoteEditor } from "../decisions/UserNoteEditor";

function message(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback;
}

function safeOutboundUrl(value: string): string | undefined {
  try {
    const url = new URL(value);
    if (!["http:", "https:"].includes(url.protocol) || url.username || url.password) {
      return undefined;
    }
    return url.href;
  } catch {
    return undefined;
  }
}

function asRecord(value: unknown): Record<string, unknown> | undefined {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : undefined;
}

function readableValue(value: unknown) {
  if (value === null || value === undefined) return "Unknown";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return "Unknown";
}

function displayAttributeValue(value: unknown) {
  const record = asRecord(value);
  if (!record) return readableValue(value);
  const parts = [readableValue(record.value)];
  if (typeof record.unit === "string" && record.unit) parts.push(record.unit);
  return parts.join(" ");
}

function originLabel(value: unknown) {
  const origin = asRecord(value)?.origin;
  if (origin === "user_correction") return "Your correction";
  if (origin === "manufacturer") return "Manufacturer listing";
  if (origin === "retailer") return "Retailer listing";
  if (origin === "structured_data") return "Structured page data";
  if (origin === "source") return "Observed on source page";
  return "Origin unknown";
}

function ProductLoadingState({ title }: { title: string }) {
  return <main className="shell loading-page"><p role="status">{title}</p></main>;
}

export function ProductDetailPage() {
  const { productId } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const variantId = searchParams.get("variant") ?? "";
  const projectId = searchParams.get("project") ?? "";
  const projectProductId = searchParams.get("project_product") ?? "";
  const productQuery = useQuery({
    queryKey: ["product", productId],
    queryFn: ({ signal }) => catalogApi.getProduct(productId!, signal),
    enabled: Boolean(productId),
    retry: false,
    refetchOnWindowFocus: false,
  });
  const product = productQuery.data;
  useEffect(() => {
    if (!product) return;
    if (!product.variants.some((variant) => variant.id === variantId)) {
      const params = new URLSearchParams(searchParams);
      const firstVariantId = product.variants[0]?.id;
      if (firstVariantId) params.set("variant", firstVariantId);
      else params.delete("variant");
      setSearchParams(params, { replace: true });
    }
  }, [product, searchParams, setSearchParams, variantId]);

  if (!productId || productQuery.isPending) return <ProductLoadingState title="Loading product details…" />;
  if (productQuery.isError || !product) {
    const missing = productQuery.error instanceof ApiRequestError && productQuery.error.status === 404;
    return (
      <main className="shell state-page">
        <p className="eyebrow">{missing ? "Product unavailable" : "Connection issue"}</p>
        <h1>{missing ? "This product can’t be opened." : "Product details could not load."}</h1>
        <p role="alert">{message(productQuery.error, "Try again in a moment.")}</p>
        {!missing && <button className="button quiet-button" onClick={() => void productQuery.refetch()}>Retry</button>}
        <Link className="back-link" to="/">Return to projects</Link>
      </main>
    );
  }

  return <ProductDetail
    product={product}
    variantId={variantId}
    projectId={projectId}
    projectProductId={projectProductId}
    setVariantId={(id) => setSearchParams((current) => {
      const params = new URLSearchParams(current);
      if (id) params.set("variant", id);
      else params.delete("variant");
      if (id !== variantId) params.delete("project_product");
      return params;
    })}
  />;
}

function ProductDetail({ product, variantId, projectId, projectProductId, setVariantId }: {
  product: ProductRead;
  variantId: string;
  projectId: string;
  projectProductId: string;
  setVariantId: (id: string) => void;
}) {
  const projectQuery = useQuery({
    queryKey: ["project", projectId],
    queryFn: ({ signal }) => projectsApi.get(projectId, signal),
    enabled: Boolean(projectId && projectProductId),
    retry: false,
  });
  const offersQuery = useInfiniteQuery({
    queryKey: ["product-offers", product.id, variantId],
    initialPageParam: undefined as string | undefined,
    queryFn: ({ signal, pageParam }) =>
      catalogApi.offers(product.id, variantId, 20, pageParam, signal),
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    enabled: Boolean(variantId),
    retry: false,
    refetchOnWindowFocus: false,
  });
  const variant = product.variants.find((item) => item.id === variantId);
  const offers = useMemo(() => {
    const pages = offersQuery.data?.pages ?? [];
    return pages.flatMap((page) => page.items);
  }, [offersQuery.data]);

  return (
    <main className="shell product-shell">
      <header className="app-header">
        <Link className="brand" to="/" aria-label="Shopping Assistant home">
          <span className="brand-mark" aria-hidden="true">S</span>
          <span>Shopping Assistant</span>
        </Link>
        <Link className="header-back" to="/">Your projects</Link>
      </header>
      <nav aria-label="Breadcrumb" className="breadcrumbs">
        <Link to="/">Projects</Link><span aria-hidden="true">/</span><span>Product</span>
      </nav>
      {projectId && <ProjectNavigation projectId={projectId} />}

      <section className="product-title-card card">
        <p className="eyebrow">Canonical product · Product revision {product.revision}</p>
        <h1>{product.canonical_name}</h1>
        <p className="product-identity-line">
          {[product.brand, product.model_family, product.category].filter(Boolean).join(" · ") || "Brand, model, and category are unknown"}
        </p>
        {variantId && <FavoriteButton variantId={variantId} />}
      </section>
      {projectId && projectProductId && variantId && <ProductResearch
        projectId={projectId}
        projectProductId={projectProductId}
      />}
      {projectId && projectProductId && projectQuery.data && (
        <section className="card product-project-state">
          <p className="eyebrow">This project’s decision</p>
          <ProductDecisionActions project={projectQuery.data} projectProductId={projectProductId} offers={offers} />
          <UserNoteEditor key={`${projectId}:${projectProductId}`} project={projectQuery.data} projectProductId={projectProductId} title="Product note" />
        </section>
      )}

      <section className="product-detail-layout">
        <div className="card product-variant-card">
          <p className="eyebrow">Product variant</p>
          {product.variants.length === 0 ? (
            <p className="quiet-state">No variant details are available yet.</p>
          ) : (
            <>
              <label className="field-label" htmlFor="product-variant">Choose a variant</label>
              <select id="product-variant" value={variantId} onChange={(event) => setVariantId(event.target.value)}>
                {product.variants.map((item) => (
                  <option key={item.id} value={item.id}>{item.display_name}</option>
                ))}
              </select>
              {variant && (
                <>
                  <h2 className="product-section-title">Identity</h2>
                  {Object.keys(variant.identity_attributes).length ? (
                    <dl className="catalog-attribute-list">
                      {Object.entries(variant.identity_attributes).map(([key, value]) => {
                        const record = asRecord(value);
                        return (
                          <div key={key}>
                            <dt>{key.replaceAll("_", " ")}</dt>
                            <dd>{displayAttributeValue(value)}</dd>
                            <small>{originLabel(value)}{typeof record?.excerpt === "string" ? ` · “${record.excerpt}”` : ""}</small>
                          </div>
                        );
                      })}
                    </dl>
                  ) : <p className="quiet-state">Variant identity details are unknown.</p>}

                  <h2 className="product-section-title">Attributes</h2>
                  {Object.keys(variant.category_attributes).length ? (
                    <dl className="catalog-attribute-list">
                      {Object.entries(variant.category_attributes).map(([key, value]) => {
                        const record = asRecord(value);
                        return (
                          <div key={key}>
                            <dt>{key.replaceAll("_", " ")}</dt>
                            <dd>{displayAttributeValue(value)}</dd>
                            <small>{originLabel(value)}{typeof record?.excerpt === "string" ? ` · “${record.excerpt}”` : ""}</small>
                          </div>
                        );
                      })}
                    </dl>
                  ) : <p className="quiet-state">No category attributes were confirmed.</p>}

                  <h2 className="product-section-title">Identifiers</h2>
                  {variant.identifiers.length ? (
                    <ul className="catalog-identifier-list">
                      {variant.identifiers.map((identifier) => (
                        <li key={identifier.id}>
                          <strong>{identifier.scheme.replaceAll("_", " ")}</strong>
                          <span>{identifier.value}</span>
                          <small>{identifier.namespace}</small>
                        </li>
                      ))}
                    </ul>
                  ) : <p className="quiet-state">No product identifiers are confirmed.</p>}
                </>
              )}
            </>
          )}
        </div>

        <section className="card product-offers-card" aria-labelledby="offer-history-title">
          <p className="eyebrow">Timestamped observations</p>
          <h2 id="offer-history-title">Retail offers</h2>
          {!variantId && <p className="quiet-state">Choose a variant to view its offers.</p>}
          {offersQuery.isPending && variantId && <p role="status">Loading offers…</p>}
          {offersQuery.isError && (
            <div className="notice error-notice">
              <p role="alert">{message(offersQuery.error, "Offer history could not load.")}</p>
              <button className="button quiet-button" type="button" onClick={() => void offersQuery.refetch()}>Retry offers</button>
            </div>
          )}
          {offersQuery.isSuccess && offers.length === 0 && (
            <div className="empty-state compact-empty">
              <h3>No offers recorded for this variant.</h3>
              <p>Price and availability stay unknown until a source page provides them.</p>
            </div>
          )}
          <ul className="retail-offer-list">
            {offers.map((offer) => {
              const href = safeOutboundUrl(offer.url);
              const observedAt = new Date(offer.observed_at);
              return (
            <li key={offer.id}>
                  <div className="retail-offer-heading">
                    <strong>{offer.retailer_name}</strong>
                    {offer.freshness === "stale" && <span className="stale-badge">Older observation</span>}
                  </div>
                  <p className="retail-offer-price">
                    {offer.amount && offer.currency ? `${offer.currency} ${offer.amount}` : "Price unknown"}
                  </p>
                  <p className="retail-offer-meta">
                    {offer.availability.replaceAll("_", " ")} · {offer.condition} · Observed {observedAt.toLocaleString()}
                  </p>
                  {href ? (
                    <a href={href} target="_blank" rel="noopener noreferrer">
                      Open retailer page<span className="sr-only"> (opens in a new tab)</span>
                    </a>
                  ) : <span className="quiet-state">Retailer link unavailable</span>}
                </li>
              );
            })}
          </ul>
          {offersQuery.hasNextPage && (
            <button
              className="button quiet-button"
              type="button"
              disabled={offersQuery.isFetchingNextPage}
              onClick={() => void offersQuery.fetchNextPage()}
            >
              {offersQuery.isFetchingNextPage ? "Loading older offers…" : "Load older offers"}
            </button>
          )}
        </section>
      </section>
    </main>
  );
}
