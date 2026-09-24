#!/usr/bin/env bash
# First-time GCP deploy for Agentic (Cloud Shell / macOS / Linux).
# Project: agentic-509610
# Never commit ANTHROPIC_API_KEY. This script reads it from the terminal.

set -euo pipefail

PROJECT_ID="${PROJECT_ID:-agentic-509610}"
REGION="${REGION:-us-central1}"
AR_REPO="${AR_REPO:-agentic}"
SECRET_NAME="${SECRET_NAME:-anthropic-api-key}"
BACKEND_SERVICE="${BACKEND_SERVICE:-agentic-backend}"
FRONTEND_SERVICE="${FRONTEND_SERVICE:-agentic-frontend}"

echo "1) Auth + project"
gcloud auth login --brief || true
gcloud config set project "$PROJECT_ID"
gcloud config set run/region "$REGION"

echo "2) Enable APIs (billing must already be on this project)"
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  secretmanager.googleapis.com \
  iam.googleapis.com \
  cloudresourcemanager.googleapis.com \
  iamcredentials.googleapis.com

echo "3) Artifact Registry"
if ! gcloud artifacts repositories describe "$AR_REPO" --location="$REGION" >/dev/null 2>&1; then
  gcloud artifacts repositories create "$AR_REPO" \
    --repository-format=docker \
    --location="$REGION" \
    --description="Agentic Cloud Run images"
fi
gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet

echo "4) Secret Manager"
if ! gcloud secrets describe "$SECRET_NAME" --project="$PROJECT_ID" >/dev/null 2>&1; then
  echo "Paste ANTHROPIC_API_KEY, then Enter (input is not stored in git):"
  read -r KEY
  printf '%s' "$KEY" | gcloud secrets create "$SECRET_NAME" --data-file=-
else
  echo "Secret $SECRET_NAME already exists."
fi

PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
COMPUTE_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
CLOUDBUILD_SA="${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com"

echo "5) IAM"
gcloud secrets add-iam-policy-binding "$SECRET_NAME" \
  --member="serviceAccount:${COMPUTE_SA}" \
  --role="roles/secretmanager.secretAccessor"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${CLOUDBUILD_SA}" \
  --role="roles/run.admin"
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${CLOUDBUILD_SA}" \
  --role="roles/iam.serviceAccountUser"
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${CLOUDBUILD_SA}" \
  --role="roles/artifactregistry.writer"
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${COMPUTE_SA}" \
  --role="roles/artifactregistry.reader"

echo "6) First deploy"
gcloud builds submit --config cloudbuild.yaml --project "$PROJECT_ID"

BACKEND_URL="$(gcloud run services describe "$BACKEND_SERVICE" --region "$REGION" --format='value(status.url)')"
FRONTEND_URL="$(gcloud run services describe "$FRONTEND_SERVICE" --region "$REGION" --format='value(status.url)')"

echo
echo "Backend:  ${BACKEND_URL}/health"
echo "Frontend: ${FRONTEND_URL}"
echo "Swagger:  ${BACKEND_URL}/docs"
