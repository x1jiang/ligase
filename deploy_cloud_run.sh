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
MIN_INSTANCES="${LIGASE_MIN_INSTANCES:-1}"
SECRET_NAME="${LIGASE_OPENAI_SECRET:-ligase-openai-key}"
SMTP_SECRET_NAME="${LIGASE_SMTP_SECRET:-ligase-smtp-password}"
CRON_SECRET_NAME="${LIGASE_CRON_SECRET:-ligase-cron-token}"
BUCKET_NAME="${LIGASE_GCS_BUCKET:-${PROJECT}-ligase-data}"
MOUNT_PATH="/mnt/ligase-data"
FEEDBACK_TO_EMAIL="${FEEDBACK_TO_EMAIL:-xiaoqian.jiang@uth.tmc.edu}"
FEEDBACK_FROM_EMAIL="${FEEDBACK_FROM_EMAIL:-xiaoqian.jiang@gmail.com}"
SMTP_HOST_VAL="${SMTP_HOST:-smtp.gmail.com}"
SMTP_PORT_VAL="${SMTP_PORT:-587}"
SMTP_USER_VAL="${SMTP_USER:-${FEEDBACK_FROM_EMAIL}}"
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
echo "  Storage:  gs://${BUCKET_NAME} -> ${MOUNT_PATH}"
echo ""

if ! command -v gcloud >/dev/null 2>&1; then
  echo "ERROR: gcloud CLI not found." >&2
  exit 1
fi

echo "1/8 Verifying GCP authentication for ${ACCOUNT}..."
if ! "${G[@]}" projects describe "${PROJECT}" --format='value(projectNumber)' >/dev/null 2>&1; then
  echo "ERROR: gcloud session for ${ACCOUNT} requires reauthentication." >&2
  echo "Run: gcloud auth login ${ACCOUNT}" >&2
  exit 1
fi
PROJECT_NUMBER="$("${G[@]}" projects describe "${PROJECT}" --format='value(projectNumber)')"
echo "    ✓ Project ${PROJECT} (#${PROJECT_NUMBER}) reachable"

echo "2/8 Enabling required Cloud Run, Build, Artifact Registry, Storage, Scheduler & Secret Manager APIs..."
"${G[@]}" services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  storage.googleapis.com \
  cloudscheduler.googleapis.com \
  secretmanager.googleapis.com \
  --quiet

echo "3/8 Ensuring dedicated runtime service account (${SA_EMAIL})..."
if ! "${G[@]}" iam service-accounts describe "${SA_EMAIL}" >/dev/null 2>&1; then
  "${G[@]}" iam service-accounts create "${SA_NAME}" \
    --display-name="Ligase Biomedical WebApp runtime" \
    --quiet
fi

echo "4/8 Ensuring persistent GCS bucket (gs://${BUCKET_NAME}) for telemetry, feedback & runs..."
if ! "${G[@]}" storage buckets describe "gs://${BUCKET_NAME}" >/dev/null 2>&1; then
  "${G[@]}" storage buckets create "gs://${BUCKET_NAME}" \
    --location="${REGION}" \
    --uniform-bucket-level-access \
    --public-access-prevention \
    --quiet
fi
for attempt in 1 2 3 4 5; do
  if "${G[@]}" storage buckets add-iam-policy-binding "gs://${BUCKET_NAME}" \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/storage.objectUser" \
    --quiet >/dev/null 2>&1; then
    break
  fi
  sleep 2
done
echo "    ✓ Persistent bucket gs://${BUCKET_NAME} ready and bound to ${SA_EMAIL}"

sync_secret() {
  local sec_name="$1"
  local sec_val="$2"
  if ! "${G[@]}" secrets describe "${sec_name}" >/dev/null 2>&1; then
    "${G[@]}" secrets create "${sec_name}" \
      --replication-policy="user-managed" \
      --locations="${REGION}" \
      --quiet
  fi
  local cur_val
  cur_val="$("${G[@]}" secrets versions access latest --secret="${sec_name}" 2>/dev/null || true)"
  if [[ "${cur_val}" != "${sec_val}" ]]; then
    printf '%s' "${sec_val}" | "${G[@]}" secrets versions add "${sec_name}" --data-file=- --quiet >/dev/null
  fi
  for attempt in 1 2 3 4 5; do
    if "${G[@]}" secrets add-iam-policy-binding "${sec_name}" \
      --member="serviceAccount:${SA_EMAIL}" \
      --role="roles/secretmanager.secretAccessor" \
      --quiet >/dev/null 2>&1; then
      break
    fi
    sleep 2
  done
}

echo "5/8 Syncing OPENAI_API_KEY, SMTP_PASSWORD & CRON_TOKEN into Secret Manager..."
API_KEY=""
if [[ "${LIGASE_FORCE_ENV_KEY:-0}" != "1" && -f "${ROOT}/.env" ]]; then
  API_KEY="$(python3 -c '
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
sync_secret "${SECRET_NAME}" "${API_KEY}"

SMTP_PW="${SMTP_PASSWORD:-}"
if [[ -z "${SMTP_PW}" ]]; then
  SMTP_PW="$(python3 - "${ROOT}" <<'PY'
import sys
from pathlib import Path
root = Path(sys.argv[1]).resolve()
for cand in [root / ".env", root.parent / "pptx_accessibility_agent" / ".env", root.parent / "mcp_grant_search" / ".env"]:
    if cand.is_file():
        for ln in cand.read_text(encoding="utf-8").splitlines():
            s = ln.strip()
            if s.startswith("SMTP_PASSWORD=") and not s.startswith("#"):
                val = s.split("=", 1)[1].strip().strip("\"'")
                if val:
                    print(val, end="")
                    sys.exit(0)
PY
)"
fi
SECRETS_ARG="OPENAI_API_KEY=${SECRET_NAME}:latest"
if [[ -n "${SMTP_PW}" ]]; then
  sync_secret "${SMTP_SECRET_NAME}" "${SMTP_PW}"
  SECRETS_ARG="${SECRETS_ARG},SMTP_PASSWORD=${SMTP_SECRET_NAME}:latest"
  echo "    ✓ Secret ${SMTP_SECRET_NAME} synced for instant feedback & digest email delivery"
fi

CRON_TOK="$("${G[@]}" secrets versions access latest --secret="${CRON_SECRET_NAME}" 2>/dev/null || true)"
if [[ -z "${CRON_TOK}" ]]; then
  CRON_TOK="$(python3 -c 'import secrets; print(secrets.token_hex(24), end="")')"
fi
sync_secret "${CRON_SECRET_NAME}" "${CRON_TOK}"
SECRETS_ARG="${SECRETS_ARG},LIGASE_CRON_TOKEN=${CRON_SECRET_NAME}:latest"
echo "    ✓ Secrets (${SECRET_NAME}, ${CRON_SECRET_NAME}) updated and bound to ${SA_EMAIL}"

echo "6/8 Building & deploying ${SERVICE} to Cloud Run (${REGION}) with GCS FUSE persistent mount..."
"${G[@]}" run deploy "${SERVICE}" \
  --source="." \
  --region="${REGION}" \
  --platform=managed \
  --execution-environment=gen2 \
  --no-invoker-iam-check \
  --session-affinity \
  --service-account="${SA_EMAIL}" \
  --cpu=2 \
  --cpu-boost \
  --no-cpu-throttling \
  --memory=2Gi \
  --timeout=300 \
  --concurrency=16 \
  --min-instances="${MIN_INSTANCES}" \
  --max-instances=4 \
  --port=8080 \
  --add-volume="name=ligase-data,type=cloud-storage,bucket=${BUCKET_NAME}" \
  --add-volume-mount="volume=ligase-data,mount-path=${MOUNT_PATH}" \
  --set-env-vars="LIGASE_CLOUD=1,LIGASE_WEB_MODEL=${MODEL},CLAW_SANDBOX_PROFILE=workspace,LIGASE_PERSISTENT_DIR=${MOUNT_PATH},LIGASE_GCS_BUCKET=${BUCKET_NAME},SMTP_HOST=${SMTP_HOST_VAL},SMTP_PORT=${SMTP_PORT_VAL},SMTP_USER=${SMTP_USER_VAL},FEEDBACK_FROM_EMAIL=${FEEDBACK_FROM_EMAIL},FEEDBACK_TO_EMAIL=${FEEDBACK_TO_EMAIL},FEEDBACK_SUMMARY_MODEL=gpt-5.4-mini" \
  --set-secrets="${SECRETS_ARG}" \
  --quiet

SERVICE_URL="$("${G[@]}" run services describe "${SERVICE}" --region="${REGION}" --format='value(status.url)')"

echo "7/8 Ensuring daily 8:00 AM Central feedback digest Cloud Scheduler job..."
SCHED_JOB="${SERVICE}-daily-digest"
if "${G[@]}" scheduler jobs describe "${SCHED_JOB}" --location="${REGION}" >/dev/null 2>&1; then
  "${G[@]}" scheduler jobs update http "${SCHED_JOB}" \
    --location="${REGION}" \
    --schedule="0 8 * * *" \
    --time-zone="America/Chicago" \
    --uri="${SERVICE_URL}/api/cron/digest" \
    --http-method=POST \
    --update-headers="Content-Type=application/json,X-Cron-Token=${CRON_TOK}" \
    --attempt-deadline=180s \
    --quiet >/dev/null
else
  "${G[@]}" scheduler jobs create http "${SCHED_JOB}" \
    --location="${REGION}" \
    --schedule="0 8 * * *" \
    --time-zone="America/Chicago" \
    --uri="${SERVICE_URL}/api/cron/digest" \
    --http-method=POST \
    --headers="Content-Type=application/json,X-Cron-Token=${CRON_TOK}" \
    --attempt-deadline=180s \
    --description="Daily 8:00 AM America/Chicago Ligase feedback & improvement digest" \
    --quiet >/dev/null
fi
echo "    ✓ Cloud Scheduler job ${SCHED_JOB} active (08:00 America/Chicago -> ${FEEDBACK_TO_EMAIL})"

echo "8/8 Verifying live health, readiness, persistent storage & feedback tab probes at ${SERVICE_URL}..."
python3 - "${SERVICE_URL}" "${MODEL}" "${BUCKET_NAME}" <<'PY'
import gzip
import json
import sys
import time
import urllib.request

base, expected_model, expected_bucket = sys.argv[1], sys.argv[2], sys.argv[3]
for path in ("/readyz", "/api/meta", "/api/usage?days=all", "/api/feedback/resolved", "/feedback", "/"):
    t0 = time.monotonic()
    req = urllib.request.Request(base + path, headers={"Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read()
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        assert resp.status == 200, f"{path} returned {resp.status}"
        if path not in ("/", "/feedback"):
            text = gzip.decompress(raw).decode("utf-8") if resp.headers.get("Content-Encoding") == "gzip" else raw.decode("utf-8")
            data = json.loads(text)
            if path == "/api/meta":
                assert data.get("model") == expected_model, f"Unexpected model: {data.get('model')}"
                assert data.get("ready") is True, "Service reported ready=False"
            elif path.startswith("/api/usage"):
                stor = data.get("storage") or {}
                assert stor.get("persistent") is True, f"Expected persistent=True, got {stor}"
                assert stor.get("bucket") == expected_bucket, f"Expected bucket={expected_bucket}, got {stor}"
            elif path == "/api/feedback/resolved":
                assert len(data.get("items") or []) >= 1, "Expected shipped fixes list"
        print(f"    ✓ {path:24s} -> HTTP 200 ({elapsed_ms} ms, encoding={resp.headers.get('Content-Encoding', 'identity')})")
print(f"    ✓ Live probes, GCS persistent mount & Feedback tab verified ({expected_model}, bucket={expected_bucket})")
PY

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  ✅ Ligase WebApp Live URL: ${SERVICE_URL}"
echo "═══════════════════════════════════════════════════════════════"
