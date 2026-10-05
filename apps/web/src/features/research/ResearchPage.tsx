import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { ApiRequestError, catalogApi, projectsApi } from "../../api/client";
import { ProjectAssistant } from "../assistant/ProjectAssistant";
import { ProductResearch } from "../products/ProductResearch";
import { ProjectNavigation } from "../projects/ProjectNavigation";

function errorText(error: unknown) {
  return error instanceof Error ? error.message : "Project research could not load.";
}

export function ResearchPage() {
  const { projectId } = useParams();
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
  const project = projectQuery.data;

  if (projectQuery.isPending) return <main className="shell loading-page"><p role="status">Loading project…</p></main>;
  if (projectQuery.isError || !project || !projectId) {
    const missing = projectQuery.error instanceof ApiRequestError && projectQuery.error.status === 404;
    return <main className="shell state-page"><h1>{missing ? "This project can’t be opened." : "Research could not load."}</h1><p role="alert">{errorText(projectQuery.error)}</p><Link to="/">Return to projects</Link></main>;
  }

  const products = productsQuery.data?.items ?? [];
  return (
    <main className="shell research-workspace-shell">
      <header className="app-header">
        <Link className="brand" to="/" aria-label="Shopping Assistant home"><span className="brand-mark" aria-hidden="true">S</span><span>Shopping Assistant</span></Link>
        <Link className="header-back" to={`/projects/${project.id}`}>Project overview</Link>
      </header>
      <nav aria-label="Breadcrumb" className="breadcrumbs"><Link to="/">Projects</Link><span aria-hidden="true">/</span><Link to={`/projects/${project.id}`}>{project.title}</Link><span aria-hidden="true">/</span><span>Research</span></nav>
      <ProjectNavigation projectId={project.id} />
      <section className="workspace-title-row">
        <div><p className="eyebrow">Evidence workspace · Project revision {project.revision}</p><h1 tabIndex={-1}>Research the exact variants</h1><p className="overview-lede">Start bounded research for a selected project variant, then inspect its fit, claims, and source excerpts.</p></div>
        <Link className="button secondary-button" to={`/projects/${project.id}/discover`}>Find more products</Link>
      </section>
      {productsQuery.isPending && <section className="card"><p role="status">Loading project variants…</p></section>}
      {productsQuery.isError && <section className="notice error-notice"><p role="alert">{errorText(productsQuery.error)}</p><button className="button quiet-button" type="button" onClick={() => void productsQuery.refetch()}>Retry</button></section>}
      {!productsQuery.isPending && !productsQuery.isError && products.length === 0 && (
        <section className="card empty-state"><h2>No project variants to research yet.</h2><p>Discover options and normalize an exact variant into this project first.</p><Link className="button primary-button" to={`/projects/${project.id}/discover`}>Go to Discover</Link></section>
      )}
      <section className="research-variant-list" aria-label="Research by project variant">
        {products.map((product) => (
          <article className="research-variant-card" key={product.id}>
            <div className="research-variant-heading">
              <div><p className="eyebrow">{product.brand ?? product.category ?? "Project variant"} · {product.variant_name}</p><h2><Link to={`/products/${product.product_id}?${new URLSearchParams({ variant: product.variant_id, project: project.id, project_product: product.id }).toString()}`}>{product.canonical_name}</Link></h2><p>{[product.model_family, product.variant_name].filter(Boolean).join(" · ")}</p></div>
              <Link className="button quiet-button small-button" to={`/projects/${project.id}/shortlist`}>Open decisions</Link>
            </div>
            <ProductResearch projectId={project.id} projectProductId={product.id} />
          </article>
        ))}
      </section>
      <ProjectAssistant project={project} />
    </main>
  );
}
