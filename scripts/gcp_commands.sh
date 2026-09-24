# Same commands as scripts/gcp_first_deploy.ps1, listed for copy-paste.
# Replace nothing except paste your Anthropic key into the secret command.
# Project: agentic-509610   Region: us-central1

gcloud auth login
gcloud config set project agentic-509610
gcloud config set run/region us-central1

gcloud services enable run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com secretmanager.googleapis.com iam.googleapis.com cloudresourcemanager.googleapis.com iamcredentials.googleapis.com

gcloud artifacts repositories create agentic --repository-format=docker --location=us-central1 --description="Agentic Cloud Run images"

gcloud auth configure-docker us-central1-docker.pkg.dev --quiet

# Create the API key secret (do not commit the key)
# Windows PowerShell:
#   Read-Host -AsSecureString | ForEach-Object { ... }  OR run scripts/gcp_first_deploy.ps1
# Cloud Shell:
printf '%s' 'PASTE_ANTHROPIC_API_KEY_HERE' | gcloud secrets create anthropic-api-key --data-file=-

PROJECT_NUMBER=$(gcloud projects describe agentic-509610 --format='value(projectNumber)')

gcloud secrets add-iam-policy-binding anthropic-api-key --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" --role=roles/secretmanager.secretAccessor

gcloud projects add-iam-policy-binding agentic-509610 --member="serviceAccount:${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com" --role=roles/run.admin
gcloud projects add-iam-policy-binding agentic-509610 --member="serviceAccount:${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com" --role=roles/iam.serviceAccountUser
gcloud projects add-iam-policy-binding agentic-509610 --member="serviceAccount:${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com" --role=roles/artifactregistry.writer

gcloud builds submit --config cloudbuild.yaml --project agentic-509610

gcloud run services describe agentic-backend --region us-central1 --format='value(status.url)'
gcloud run services describe agentic-frontend --region us-central1 --format='value(status.url)'

# Optional: CI/CD on push (after the GitHub repo is connected in Cloud Build):
# Console: https://console.cloud.google.com/cloud-build/triggers?project=agentic-509610
# Create trigger: repo KRRamanathan/Agentic, branch ^main$, config cloudbuild.yaml
