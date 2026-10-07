#!/usr/bin/env bash
set -euo pipefail

required=(
  VITE_API_BASE_URL
  VITE_FIREBASE_API_KEY
  VITE_FIREBASE_AUTH_DOMAIN
  VITE_FIREBASE_PROJECT_ID
  VITE_FIREBASE_APP_ID
)
for name in "${required[@]}"; do
  if [[ -z "${!name:-}" ]]; then
    echo "Required public build setting is missing: ${name}" >&2
    exit 2
  fi
  if [[ "${!name}" == *REPLACE_WITH* ]]; then
    echo "Replace the placeholder public build setting: ${name}" >&2
    exit 2
  fi
done

if [[ "$VITE_API_BASE_URL" != https://* ]]; then
  echo "VITE_API_BASE_URL must use HTTPS for cloud builds" >&2
  exit 2
fi

cd "$(dirname "$0")/../apps/web"
pnpm build
