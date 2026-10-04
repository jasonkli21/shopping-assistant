# API Types

TypeScript API transport types are committed in [`src/index.ts`](src/index.ts) and generated from FastAPI's OpenAPI schema.

The API schemas remain the source of truth; do not hand-maintain a duplicate domain model here. From the repository root, run `make api-types` to regenerate and `make api-types-check` to verify the committed output. CI runs the check.
