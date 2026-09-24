# First-time GCP deploy for Agentic (Windows PowerShell).
# Project already exists: agentic-509610
# Do not put ANTHROPIC_API_KEY in this file. You will be prompted.

$ErrorActionPreference = "Stop"

$PROJECT_ID = "agentic-509610"
$REGION = "us-central1"
$AR_REPO = "agentic"
$SECRET_NAME = "anthropic-api-key"
$BACKEND_SERVICE = "agentic-backend"
$FRONTEND_SERVICE = "agentic-frontend"

Write-Host "1) Auth + project"
gcloud auth login
gcloud config set project $PROJECT_ID
gcloud config set run/region $REGION

Write-Host "2) Enable APIs (billing must already be on this project)"
gcloud services enable `
  run.googleapis.com `
  artifactregistry.googleapis.com `
  cloudbuild.googleapis.com `
  secretmanager.googleapis.com `
  iam.googleapis.com `
  cloudresourcemanager.googleapis.com `
  iamcredentials.googleapis.com

Write-Host "3) Artifact Registry"
gcloud artifacts repositories describe $AR_REPO --location=$REGION 2>$null
if ($LASTEXITCODE -ne 0) {
  gcloud artifacts repositories create $AR_REPO `
    --repository-format=docker `
    --location=$REGION `
    --description="Agentic Cloud Run images"
}
gcloud auth configure-docker "$REGION-docker.pkg.dev" --quiet

Write-Host "4) Secret Manager (paste key when prompted; it is not echoed to git)"
$exists = gcloud secrets describe $SECRET_NAME --project=$PROJECT_ID 2>$null
if ($LASTEXITCODE -ne 0) {
  $secure = Read-Host "Enter ANTHROPIC_API_KEY" -AsSecureString
  $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
  $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
  $plain | gcloud secrets create $SECRET_NAME --data-file=-
  [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
} else {
  Write-Host "Secret $SECRET_NAME already exists. To rotate: gcloud secrets versions add $SECRET_NAME --data-file=-"
}

$PROJECT_NUMBER = gcloud projects describe $PROJECT_ID --format="value(projectNumber)"
$COMPUTE_SA = "$PROJECT_NUMBER-compute@developer.gserviceaccount.com"
$CLOUDBUILD_SA = "$PROJECT_NUMBER@cloudbuild.gserviceaccount.com"

Write-Host "5) IAM: Cloud Run runtime can read the secret; Cloud Build can deploy"
gcloud secrets add-iam-policy-binding $SECRET_NAME `
  --member="serviceAccount:$COMPUTE_SA" `
  --role="roles/secretmanager.secretAccessor"

gcloud projects add-iam-policy-binding $PROJECT_ID `
  --member="serviceAccount:$CLOUDBUILD_SA" `
  --role="roles/run.admin"
gcloud projects add-iam-policy-binding $PROJECT_ID `
  --member="serviceAccount:$CLOUDBUILD_SA" `
  --role="roles/iam.serviceAccountUser"
gcloud projects add-iam-policy-binding $PROJECT_ID `
  --member="serviceAccount:$CLOUDBUILD_SA" `
  --role="roles/artifactregistry.writer"
gcloud projects add-iam-policy-binding $PROJECT_ID `
  --member="serviceAccount:$COMPUTE_SA" `
  --role="roles/artifactregistry.reader"

Write-Host "6) First deploy via Cloud Build (uses cloudbuild.yaml)"
gcloud builds submit --config cloudbuild.yaml --project $PROJECT_ID

$BACKEND_URL = gcloud run services describe $BACKEND_SERVICE --region $REGION --format="value(status.url)"
$FRONTEND_URL = gcloud run services describe $FRONTEND_SERVICE --region $REGION --format="value(status.url)"

Write-Host ""
Write-Host "Backend:  $BACKEND_URL/health"
Write-Host "Frontend: $FRONTEND_URL"
Write-Host "Swagger:  $BACKEND_URL/docs"
