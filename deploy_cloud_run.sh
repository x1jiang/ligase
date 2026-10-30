#!/usr/bin/env bash
# Deploy Ligase WebApp (with gpt-6-luna) to Google Cloud Run under xjiang2@uth.edu.
# Uses Secret Manager for OPENAI_API_KEY and Cloud Run --no-invoker-iam-check for UTHealth GCP org compatibility.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

ACCOUNT="${LIGASE_DEPLOY_ACCOUNT:-xjiang2@uth.edu}"
PROJECT="${LIGASE_DEPLOY_PROJECT:-sbmi-jiang-ai-testing01}"
REGION="${LIGASE_DEPLOY_REGION:-us-central1}"
SERVICE="${LIGASE_DEPLOY_SERVICE:-ligase}"
MODEL="${LIGASE_WEB_MODEL:-gpt-6-luna}"
SECRET_NAME="${LIGASE_OPENAI_SECRET:-ligase-openai-key}"
SA_NAME="${SERVICE}-sa"
SA_EMAIL="${SA_NAME}@${PROJECT}.iam.gserviceaccount.com"

G=(gcloud "--account=${ACCOUNT}" "--project=${PROJECT}")

echo "═══════════════════════════════════════════════════════════════"
echo "  🧬 Ligase Biomedical WebApp — Cloud Run Deployment"
echo "═══════════════════════════════════════════════════════════════"
echo "  Account:  ${ACCOUNT}"
echo "  Project:  ${PROJECT}"
echo "  Region:   ${REGION}"
echo "  Service:  ${SERVICE}"
echo "  Model:    ${MODEL}"
echo ""

if ! command -v gcloud >/dev/null 2>&1; then
  echo "ERROR: gcloud CLI not found." >&2
  exit 1
fi

echo "1/6 Verifying GCP authentication for ${ACCOUNT}..."
if ! "${G[@]}" projects describe "${PROJECT}" --format='value(projectNumber)' >/dev/null 2>&1; then
  echo "ERROR: gcloud session for ${ACCOUNT} requires reauthentication." >&2
  echo "Run: gcloud auth login ${ACCOUNT}" >&2
  exit 1
fi
PROJECT_NUMBER="$("${G[@]}" projects describe "${PROJECT}" --format='value(projectNumber)')"
echo "    ✓ Project ${PROJECT} (#${PROJECT_NUMBER}) reachable"

echo "2/6 Enabling required Cloud Run, Build, Artifact Registry & Secret Manager APIs..."
"${G[@]}" services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  --quiet

echo "3/6 Ensuring dedicated runtime service account (${SA_EMAIL})..."
if ! "${G[@]}" iam service-accounts describe "${SA_EMAIL}" >/dev/null 2>&1; then
  "${G[@]}" iam service-accounts create "${SA_NAME}" \
    --display-name="Ligase Biomedical WebApp runtime" \
    --quiet
fi

echo "4/6 Syncing OPENAI_API_KEY into Secret Manager (${SECRET_NAME})..."
API_KEY=""
if [[ "${LIGASE_FORCE_ENV_KEY:-0}" != "1" && -f "${ROOT}/.env" ]]; then
  API_KEY="$("${ROOT}/.venv/bin/python" -c '
from dotenv import dotenv_values
v = dotenv_values(".env").get("OPENAI_API_KEY", "").strip()
print(v, end="")
' 2>/dev/null || python3 -c '
for line in open(".env"):
    line = line.strip()
    if line.startswith("OPENAI_API_KEY="):
        print(line.split("=", 1)[1].strip().strip("\"\x27"), end="")
        break
')"
fi
if [[ -z "${API_KEY}" ]]; then
  API_KEY="${OPENAI_API_KEY:-}"
fi
if [[ -z "${API_KEY}" ]]; then
  echo "ERROR: OPENAI_API_KEY not found in environment or .env" >&2
  exit 1
fi

if ! "${G[@]}" secrets describe "${SECRET_NAME}" >/dev/null 2>&1; then
  "${G[@]}" secrets create "${SECRET_NAME}" \
    --replication-policy="user-managed" \
    --locations="${REGION}" \
    --quiet
fi
CURRENT_SECRET="$("${G[@]}" secrets versions access latest --secret="${SECRET_NAME}" 2>/dev/null || true)"
if [[ "${CURRENT_SECRET}" != "${API_KEY}" ]]; then
  printf '%s' "${API_KEY}" | "${G[@]}" secrets versions add "${SECRET_NAME}" --data-file=- --quiet >/dev/null
fi
for attempt in 1 2 3 4 5; do
  if "${G[@]}" secrets add-iam-policy-binding "${SECRET_NAME}" \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/secretmanager.secretAccessor" \
    --quiet >/dev/null 2>&1; then
    break
  fi
  sleep 2
done
echo "    ✓ Secret ${SECRET_NAME} updated and bound to ${SA_EMAIL}"

echo "5/6 Building & deploying ${SERVICE} to Cloud Run (${REGION})..."
"${G[@]}" run deploy "${SERVICE}" \
  --source="." \
  --region="${REGION}" \
  --platform=managed \
  --execution-environment=gen2 \
  --no-invoker-iam-check \
  --service-account="${SA_EMAIL}" \
  --cpu=2 \
  --memory=2Gi \
  --timeout=300 \
  --concurrency=16 \
  --min-instances=0 \
  --max-instances=4 \
  --port=8080 \
  --set-env-vars="LIGASE_CLOUD=1,LIGASE_WEB_MODEL=${MODEL},CLAW_SANDBOX_PROFILE=workspace" \
  --set-secrets="OPENAI_API_KEY=${SECRET_NAME}:latest" \
  --quiet

SERVICE_URL="$("${G[@]}" run services describe "${SERVICE}" --region="${REGION}" --format='value(status.url)')"

echo "6/6 Verifying live health & readiness probes at ${SERVICE_URL}..."
python3 - "${SERVICE_URL}" "${MODEL}" <<'PY'
import json
import sys
import urllib.request

base, expected_model = sys.argv[1], sys.argv[2]
# Note: Cloud Run's Google Front End reserves /healthz at the edge; probe /readyz and /api/meta.
for path in ("/readyz", "/api/meta"):
    with urllib.request.urlopen(base + path, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        assert resp.status == 200, f"{path} returned {resp.status}"
        if path == "/api/meta":
            assert data.get("model") == expected_model, f"Unexpected model: {data.get('model')}"
            assert data.get("ready") is True, "Service reported ready=False"
print(f"    ✓ Live probes verified ({expected_model}, ready=True)")
PY

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  ✅ Ligase WebApp Live URL: ${SERVICE_URL}"
echo "═══════════════════════════════════════════════════════════════"
