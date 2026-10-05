import { useInfiniteQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { catalogApi } from "../../api/client";
import { FavoriteButton } from "./FavoriteButton";

function message(error: unknown) {
  return error instanceof Error ? error.message : "Saved products could not load.";
}

export function SavedProductsPage() {
  const products = useInfiniteQuery({
    queryKey: ["saved-products"],
    initialPageParam: undefined as string | undefined,
    queryFn: ({ signal, pageParam }) => catalogApi.listSavedProducts(100, pageParam, signal),
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    retry: false,
  });
  const savedProducts = products.data?.pages.flatMap((page) => page.items) ?? [];
  return (
    <main className="shell saved-products-shell">
      <header className="app-header">
        <Link className="brand" to="/" aria-label="Shopping Assistant home"><span className="brand-mark" aria-hidden="true">S</span><span>Shopping Assistant</span></Link>
        <Link className="header-back" to="/">Projects</Link>
      </header>
      <nav aria-label="Breadcrumb" className="breadcrumbs"><Link to="/">Projects</Link><span aria-hidden="true">/</span><span>Saved Products</span></nav>
      <section className="workspace-title-row"><div><p className="eyebrow">Private to your account</p><h1 tabIndex={-1}>Saved Products</h1><p className="overview-lede">Favorites stay separate from project decisions and refer to an exact catalog variant.</p></div></section>
      {products.isPending && <p className="quiet-state" role="status">Loading saved products…</p>}
      {products.isError && <div className="notice error-notice"><p role="alert">{message(products.error)}</p><button className="button quiet-button" type="button" onClick={() => void products.refetch()}>Retry</button></div>}
      {products.isSuccess && savedProducts.length === 0 && <section className="card empty-state"><h2>No favorites saved yet.</h2><p>Save an exact variant from its product detail page to keep it here.</p><Link className="button secondary-button" to="/">Browse projects</Link></section>}
      {products.isSuccess && savedProducts.length > 0 && (
        <ul className="saved-products-list">
          {savedProducts.map((product) => (
            <li className="card saved-product-card" key={product.variant_id}>
              <div><p className="eyebrow">{product.brand ?? product.category ?? "Product"} · Exact variant</p><h2><Link to={`/products/${product.product_id}?variant=${encodeURIComponent(product.variant_id)}`}>{product.canonical_name}</Link></h2><p>{product.variant_name}</p>{Object.keys(product.identity_attributes).length > 0 && <ul className="saved-product-identity">{Object.entries(product.identity_attributes).map(([key, value]) => <li key={key}><strong>{key.replaceAll("_", " ")}:</strong> {typeof value === "object" && value !== null && "value" in value ? String((value as { value: unknown }).value) : String(value)}</li>)}</ul>}<small>Saved {product.updated_at ? new Date(product.updated_at).toLocaleDateString() : "previously"}</small></div>
              <FavoriteButton variantId={product.variant_id} />
            </li>
          ))}
        </ul>
      )}
      {products.hasNextPage && <button className="button quiet-button" type="button" disabled={products.isFetchingNextPage} onClick={() => void products.fetchNextPage()}>{products.isFetchingNextPage ? "Loading more saved products…" : "Load more saved products"}</button>}
    </main>
  );
}
