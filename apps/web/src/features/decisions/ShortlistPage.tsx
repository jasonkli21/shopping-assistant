import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { ApiRequestError, decisionsApi, projectsApi } from "../../api/client";
import { ProjectAssistant } from "../assistant/ProjectAssistant";
import { ProjectNavigation } from "../projects/ProjectNavigation";
import { ProductDecisionActions } from "./ProductDecisionActions";
import { UserNoteEditor } from "./UserNoteEditor";

function errorText(error: unknown) {
  return error instanceof Error ? error.message : "This project view could not load.";
}

export function ShortlistPage() {
  const { projectId } = useParams();
  const projectQuery = useQuery({
    queryKey: ["project", projectId],
    queryFn: ({ signal }) => projectsApi.get(projectId!, signal),
    enabled: Boolean(projectId),
    retry: false,
  });
  const shortlistQuery = useQuery({
    queryKey: ["shortlist", projectId],
    queryFn: ({ signal }) => decisionsApi.listShortlist(projectId!, signal),
    enabled: Boolean(projectId && projectQuery.data),
    retry: false,
  });
  const rejectionsQuery = useQuery({
    queryKey: ["rejections", projectId],
    queryFn: ({ signal }) => decisionsApi.listRejections(projectId!, signal),
    enabled: Boolean(projectId && projectQuery.data),
    retry: false,
  });
  const project = projectQuery.data;

  if (projectQuery.isPending) return <main className="shell loading-page"><p role="status">Loading project…</p></main>;
  if (projectQuery.isError || !project || !projectId) {
    const missing = projectQuery.error instanceof ApiRequestError && projectQuery.error.status === 404;
    return <main className="shell state-page"><h1>{missing ? "This project can’t be opened." : "Shortlist could not load."}</h1><p role="alert">{errorText(projectQuery.error)}</p><Link to="/">Return to projects</Link></main>;
  }

  const shortlisted = shortlistQuery.data?.items ?? [];
  const rejected = rejectionsQuery.data?.items ?? [];
  return (
    <main className="shell decision-workspace-shell">
      <header className="app-header">
        <Link className="brand" to="/" aria-label="Shopping Assistant home"><span className="brand-mark" aria-hidden="true">S</span><span>Shopping Assistant</span></Link>
        <Link className="header-back" to={`/projects/${project.id}`}>Project overview</Link>
      </header>
      <nav aria-label="Breadcrumb" className="breadcrumbs"><Link to="/">Projects</Link><span aria-hidden="true">/</span><Link to={`/projects/${project.id}`}>{project.title}</Link><span aria-hidden="true">/</span><span>Shortlist</span></nav>
      <ProjectNavigation projectId={project.id} />
      <section className="workspace-title-row">
        <div><p className="eyebrow">Decision workspace · Revision {project.revision}</p><h1 tabIndex={-1}>Your shortlist</h1><p className="overview-lede">Keep the variants you’re seriously considering, with your rationale and concerns beside them.</p></div>
        <Link className="button primary-button" to={`/projects/${project.id}/compare`}>Compare variants</Link>
      </section>

      <section className="card shortlist-section" aria-labelledby="shortlist-title">
        <div className="section-heading"><div><p className="eyebrow">Decision set</p><h2 id="shortlist-title">Shortlisted products</h2></div><span className="count-pill">{shortlisted.length}</span></div>
        {shortlistQuery.isPending && <p role="status">Loading shortlist…</p>}
        {shortlistQuery.isError && <div className="notice error-notice"><p role="alert">{errorText(shortlistQuery.error)}</p><button className="button quiet-button" type="button" onClick={() => void shortlistQuery.refetch()}>Retry shortlist</button></div>}
        {!shortlistQuery.isPending && !shortlistQuery.isError && shortlisted.length === 0 && (
          <div className="empty-state"><h3>No products shortlisted yet.</h3><p>Normalize a candidate, then choose Shortlist when you’re ready to keep a variant in the decision set.</p><Link className="button secondary-button" to={`/projects/${project.id}/discover`}>Explore products</Link></div>
        )}
        <ul className="shortlist-product-list">
          {shortlisted.map(({ product, decision }) => (
            <li className="card shortlist-product-card" key={product.id}>
              <div className="shortlist-product-heading">
                <div>
                  <p className="eyebrow">Exact variant · {product.variant_name}</p>
                  <h3><Link to={`/products/${product.product_id}?${new URLSearchParams({ variant: product.variant_id, project: project.id, project_product: product.id }).toString()}`}>{product.canonical_name}</Link></h3>
                  <p>{[product.brand, product.model_family, product.variant_name].filter(Boolean).join(" · ")}</p>
                </div>
                {product.offers[0] && <div className="shortlist-offer"><strong>{product.offers[0].amount && product.offers[0].currency ? `${product.offers[0].currency} ${product.offers[0].amount}` : "Price unknown"}</strong><small>{product.offers[0].retailer_name} · observed {new Date(product.offers[0].observed_at).toLocaleDateString()}</small></div>}
              </div>
              {decision.reason && <p className="decision-rationale"><strong>Why it’s here:</strong> {decision.reason}</p>}
              {decision.concerns.length > 0 && <p className="decision-rationale"><strong>Concerns:</strong> {decision.concerns.join(" · ")}</p>}
              <ProductDecisionActions project={project} projectProductId={product.id} />
              <UserNoteEditor project={project} projectProductId={product.id} title="Shortlist note" />
            </li>
          ))}
        </ul>
      </section>

      <section className="card shortlist-section" aria-labelledby="rejections-title">
        <div className="section-heading"><div><p className="eyebrow">Kept in project history</p><h2 id="rejections-title">Rejected products</h2></div><span className="count-pill">{rejected.length}</span></div>
        <p className="quiet-state">Rejection reasons stay project-specific and can be undone later.</p>
        {rejectionsQuery.isPending && <p role="status">Loading rejected products…</p>}
        {rejectionsQuery.isError && <p className="field-error" role="alert">{errorText(rejectionsQuery.error)}</p>}
        <ul className="rejected-product-list">
          {rejected.map(({ product, decision }) => (
            <li key={product.id}>
              <Link to={`/products/${product.product_id}?${new URLSearchParams({ variant: product.variant_id, project: project.id, project_product: product.id }).toString()}`}>{product.canonical_name} · {product.variant_name}</Link>
              <span>{decision.rejection_reason?.replaceAll("_", " ") ?? "Reason unknown"}</span>
              {decision.reason && <small>{decision.reason}</small>}
              <ProductDecisionActions project={project} projectProductId={product.id} />
            </li>
          ))}
        </ul>
      </section>
      <ProjectAssistant project={project} />
    </main>
  );
}
