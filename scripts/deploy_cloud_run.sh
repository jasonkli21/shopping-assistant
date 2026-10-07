#!/usr/bin/env bash
set -euo pipefail

required=(
  GCP_PROJECT_ID
  GCP_REGION
  CLOUD_RUN_SERVICE
  CLOUD_RUN_SERVICE_ACCOUNT
  CLOUD_RUN_MAX_INSTANCES
  CLOUD_RUN_CONCURRENCY
  CLOUD_RUN_TIMEOUT_SECONDS
  CLOUD_RUN_CPU
  CLOUD_RUN_MEMORY
  IMAGE
  FIREBASE_PROJECT_ID
  FIREBASE_OWNER_UID
  LOCAL_OWNER_ID
  CORS_ORIGIN
  DATABASE_URL_SECRET
  DATABASE_URL_SECRET_VERSION
  TAVILY_API_KEY_SECRET
  TAVILY_API_KEY_SECRET_VERSION
)
for name in "${required[@]}"; do
  if [[ -z "${!name:-}" ]]; then
    echo "Required deployment setting is missing: ${name}" >&2
    exit 2
  fi
done

if [[ "$CORS_ORIGIN" != https://* || "$CORS_ORIGIN" == *,* || "$CORS_ORIGIN" == *\** ]]; then
  echo "CORS_ORIGIN must be one exact HTTPS origin" >&2
  exit 2
fi
if [[ ! "$IMAGE" =~ @sha256:[a-f0-9]{64}$ ]]; then
  echo "IMAGE must be pinned to an immutable sha256 digest" >&2
  exit 2
fi
if [[ ! "$LOCAL_OWNER_ID" =~ ^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$ ]]; then
  echo "LOCAL_OWNER_ID must be the existing owner UUID" >&2
  exit 2
fi
if [[ ! "$CLOUD_RUN_MAX_INSTANCES" =~ ^([1-9]|1[0-9]|20)$ ]]; then
  echo "CLOUD_RUN_MAX_INSTANCES must be an integer from 1 to 20" >&2
  exit 2
fi
if [[ ! "$CLOUD_RUN_CONCURRENCY" =~ ^([1-9]|1[0-6])$ ]]; then
  echo "CLOUD_RUN_CONCURRENCY must be an integer from 1 to 16" >&2
  exit 2
fi
if [[ ! "$CLOUD_RUN_TIMEOUT_SECONDS" =~ ^([3-9][0-9]|[1-9][0-9]{2,3})$ || "$CLOUD_RUN_TIMEOUT_SECONDS" -gt 3600 ]]; then
  echo "CLOUD_RUN_TIMEOUT_SECONDS must be between 30 and 3600" >&2
  exit 2
fi
if [[ "$DATABASE_URL_SECRET_VERSION" == latest || "$TAVILY_API_KEY_SECRET_VERSION" == latest ]]; then
  echo "Pin Secret Manager versions instead of using latest" >&2
  exit 2
fi

# `external` prevents fake generation; it still selects the fail-closed
# unavailable client until a supported Personal AI transport is implemented.
gcloud run deploy "$CLOUD_RUN_SERVICE" \
  --project "$GCP_PROJECT_ID" \
  --region "$GCP_REGION" \
  --image "$IMAGE" \
  --service-account "$CLOUD_RUN_SERVICE_ACCOUNT" \
  --allow-unauthenticated \
  --min 0 \
  --max "$CLOUD_RUN_MAX_INSTANCES" \
  --concurrency "$CLOUD_RUN_CONCURRENCY" \
  --timeout "${CLOUD_RUN_TIMEOUT_SECONDS}s" \
  --cpu "$CLOUD_RUN_CPU" \
  --memory "$CLOUD_RUN_MEMORY" \
  --no-cpu-throttling \
  --port 8080 \
  --set-env-vars "ENVIRONMENT=production,AUTH_MODE=firebase,FIREBASE_PROJECT_ID=${FIREBASE_PROJECT_ID},FIREBASE_OWNER_UID=${FIREBASE_OWNER_UID},LOCAL_OWNER_ID=${LOCAL_OWNER_ID},CORS_ORIGINS=${CORS_ORIGIN},SEARCH_PROVIDER=tavily,PERSONAL_AI_MODE=external,DB_POOL_SIZE=2,DB_MAX_OVERFLOW=0" \
  --set-secrets "DATABASE_URL=${DATABASE_URL_SECRET}:${DATABASE_URL_SECRET_VERSION},TAVILY_API_KEY=${TAVILY_API_KEY_SECRET}:${TAVILY_API_KEY_SECRET_VERSION}"
