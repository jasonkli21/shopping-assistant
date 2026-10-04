# Technology Choices

## Locked defaults

| Layer | Choice |
|---|---|
| Frontend | React + TypeScript + Vite |
| Routing | React Router |
| Server state | TanStack Query |
| Backend | Python 3.12+ + FastAPI |
| Validation/config | Pydantic / pydantic-settings |
| ORM | SQLAlchemy 2 |
| Migrations | Alembic |
| Local database | PostgreSQL 16 in Docker |
| Cloud database | Neon PostgreSQL |
| Backend hosting | Google Cloud Run |
| Frontend hosting | Firebase Hosting |
| AI boundary | personal-ai-system over HTTP |
| Assistant streaming | Server-Sent Events |
| Initial search adapter | Tavily |
| Secondary search adapter | Brave later |
| HTTP retrieval | httpx-based retriever |
| Dynamic browser fallback | Playwright later only if needed |
| Background execution | in-process first, Cloud Run Jobs later |
| Python tooling | uv, Ruff, pytest |
| Frontend tooling | pnpm, ESLint, Vitest |
| CI | GitHub Actions |

## Why PostgreSQL

Shopping data is naturally relational: projects, products, variants, offers, claims, evidence, comparisons, research runs, and project-product relationships. PostgreSQL also supports flexible JSONB fields for category-specific product attributes.

Do not adopt Firestore simply to align with another repository.

## Why modular monolith

This is a personal application with complex domain logic but modest deployment scale. Strong module boundaries matter; distributed systems complexity does not.

## Why SPA

The application has little SEO need, the backend is already independent, and AI streaming/research state are naturally client-driven. Vite keeps local development simple.

## Deferred decisions

Do not lock these prematurely:

- exact long-term search provider mix;
- browser retrieval implementation;
- vector/embedding technology;
- object storage;
- official retailer APIs;
- queue infrastructure;
- whether generic research later moves to personal-ai-system;
- Terraform/IaC layout.
