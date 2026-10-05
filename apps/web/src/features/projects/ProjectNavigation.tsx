import { NavLink } from "react-router-dom";

const sections = [
  { label: "Overview", path: "" },
  { label: "Discover", path: "/discover" },
  { label: "Compare", path: "/compare" },
  { label: "Shortlist", path: "/shortlist" },
  { label: "Research", path: "/research" },
];

export function ProjectNavigation({ projectId }: { projectId: string }) {
  const base = `/projects/${projectId}`;
  return (
    <nav className="project-workspace-nav" aria-label="Project workspace">
      {sections.map((section) => (
        <NavLink
          key={section.label}
          to={`${base}${section.path}`}
          end={!section.path}
          className={({ isActive }) => `project-workspace-link${isActive ? " active" : ""}`}
        >
          {section.label}
        </NavLink>
      ))}
    </nav>
  );
}
