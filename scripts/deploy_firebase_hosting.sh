#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${FIREBASE_PROJECT_ID:-}" ]]; then
  echo "Set FIREBASE_PROJECT_ID to the verified Hosting project." >&2
  exit 2
fi
if [[ ! -f apps/web/dist/index.html ]]; then
  echo "Build apps/web first with scripts/build_cloud_web.sh." >&2
  exit 2
fi

firebase deploy --project "$FIREBASE_PROJECT_ID" --only hosting
