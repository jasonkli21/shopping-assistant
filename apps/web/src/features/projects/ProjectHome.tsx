import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { ApiRequestError, ProjectCreate, projectsApi } from "../../api/client";

function fieldMessage(error: unknown, field: string): string | undefined {
  if (!(error instanceof ApiRequestError) || !Array.isArray(error.details)) return undefined;
  const match = error.details.find(
    (item): item is { field: string; message: string } =>
      typeof item === "object" &&
      item !== null &&
      "field" in item &&
      "message" in item &&
      typeof item.field === "string" &&
      typeof item.message === "string" &&
      item.field.endsWith(field),
  );
  return match?.message;
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "The request could not be completed.";
}

export function ProjectHome() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const titleRef = useRef<HTMLInputElement>(null);
  const [title, setTitle] = useState("");
  const [goal, setGoal] = useState("");

  const recentProjects = useQuery({
    queryKey: ["projects"],
    queryFn: () => projectsApi.list(10),
    retry: false,
    refetchOnWindowFocus: false,
  });

  useEffect(() => {
    titleRef.current?.focus();
  }, []);

  const createProject = useMutation({
    mutationFn: (command: ProjectCreate) => projectsApi.create(command),
    onSuccess: async (project) => {
      setTitle("");
      setGoal("");
      await queryClient.invalidateQueries({ queryKey: ["projects"] });
      navigate(`/projects/${project.id}`);
    },
  });

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (createProject.isPending) return;
    const command: ProjectCreate = { title: title.trim(), goal: goal.trim() };
    createProject.mutate(command);
  }

  return (
    <main className="shell home-shell">
      <header className="app-header">
        <Link className="brand" to="/" aria-label="Shopping Assistant home">
          <span className="brand-mark" aria-hidden="true">S</span>
          <span>Shopping Assistant</span>
        </Link>
        <div className="header-links">
          <Link className="header-caption" to="/profile">Shopping Profile</Link>
          <Link className="header-caption saved-products-header-link" to="/saved-products">Saved Products</Link>
        </div>
      </header>

      <section className="home-intro" aria-labelledby="home-title">
        <p className="eyebrow">A place for your next decision</p>
        <h1 id="home-title">Make room for a better choice.</h1>
        <p className="intro-copy">
          Give a shopping need its own project. Keep the budget, must-haves, and notes together
          while you figure out what matters.
        </p>
      </section>

      <div className="home-grid">
        <section className="card create-card" aria-labelledby="create-title">
          <div className="section-heading">
            <span className="step-mark" aria-hidden="true">01</span>
            <div>
              <p className="eyebrow">Start with what you need</p>
              <h2 id="create-title">Create a shopping project</h2>
            </div>
          </div>
          <form onSubmit={submit}>
            <fieldset className="pending-fieldset" disabled={createProject.isPending}>
              <legend className="sr-only">New project details</legend>
            <label className="field-label" htmlFor="project-title">Project name</label>
            <input
              ref={titleRef}
              id="project-title"
              name="title"
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              maxLength={200}
              required
              autoComplete="off"
              aria-describedby={fieldMessage(createProject.error, "title") ? "title-error" : undefined}
            />
            {fieldMessage(createProject.error, "title") && (
              <p id="title-error" className="field-error">{fieldMessage(createProject.error, "title")}</p>
            )}

            <label className="field-label" htmlFor="project-goal">What are you looking for?</label>
            <textarea
              id="project-goal"
              name="goal"
              value={goal}
              onChange={(event) => setGoal(event.target.value)}
              maxLength={4000}
              rows={4}
              required
              placeholder="A cordless vacuum for a small apartment that handles pet hair."
              aria-describedby={fieldMessage(createProject.error, "goal") ? "goal-error" : undefined}
            />
            {fieldMessage(createProject.error, "goal") && (
              <p id="goal-error" className="field-error">{fieldMessage(createProject.error, "goal")}</p>
            )}
            </fieldset>

            {createProject.isError && (
              <p className="notice error-notice" role="alert">
                {errorMessage(createProject.error)} Your entries are still here; you can retry.
              </p>
            )}

            <button className="button primary-button" type="submit" disabled={createProject.isPending}>
              {createProject.isPending ? "Creating project…" : "Create project"}
            </button>
            {createProject.isPending && <p className="pending-copy" role="status">Saving your project…</p>}
          </form>
        </section>

        <section className="card recent-card" aria-labelledby="recent-title">
          <div className="section-heading recent-heading">
            <span className="step-mark muted-mark" aria-hidden="true">02</span>
            <div>
              <p className="eyebrow">Pick up where you left off</p>
              <h2 id="recent-title">Recent projects</h2>
            </div>
          </div>

          {recentProjects.isPending && <p className="quiet-state" role="status">Loading your projects…</p>}
          {recentProjects.isError && (
            <div className="notice error-notice" role="alert">
              <p>Recent projects could not load. Your new project form is ready.</p>
              <button className="button quiet-button" type="button" onClick={() => void recentProjects.refetch()}>
                Retry loading projects
              </button>
            </div>
          )}
          {recentProjects.isSuccess && recentProjects.data.items.length === 0 && (
            <div className="empty-state">
              <span className="empty-icon" aria-hidden="true">✳</span>
              <h3>Your first project starts here</h3>
              <p>Projects keep your goal, budget, and requirements in one durable place.</p>
            </div>
          )}
          {recentProjects.isSuccess && recentProjects.data.items.length > 0 && (
            <ul className="project-list">
              {recentProjects.data.items.map((project) => (
                <li key={project.id}>
                  <Link className="project-link" to={`/projects/${project.id}`}>
                    <span className="project-link-copy">
                      <strong>{project.title}</strong>
                      <span>{project.goal}</span>
                    </span>
                    <span className={`status-pill status-${project.status}`}>{project.status}</span>
                    <span className="chevron" aria-hidden="true">›</span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      <footer className="page-footer">Your shopping research stays organized around your project.</footer>
    </main>
  );
}
