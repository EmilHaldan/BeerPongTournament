# Beer Pong Tournament – Infrastructure

Terraform configuration for provisioning all Azure resources.

## Resources Created

| Resource | Purpose |
|---|---|
| Resource Group | Single RG for everything |
| Cosmos DB (serverless NoSQL) | Match data storage |
| Container Registry (Basic) | Backend Docker images |
| Log Analytics Workspace | Container App logs |
| Container App Environment | Hosting environment |
| Container App | Backend FastAPI server (scale 0–1) |
| Static Web App (Free) | Frontend hosting |

## Usage

```bash
# Initialise
cd infra
terraform init

# Plan
terraform plan -var-file=env/dev.tfvars -var="subscription_id=YOUR_SUB_ID" -var="admin_token=YOUR_TOKEN"

# Apply
terraform apply -var-file=env/dev.tfvars -var="subscription_id=YOUR_SUB_ID" -var="admin_token=YOUR_TOKEN"

# Destroy (after tournament)
terraform destroy -var-file=env/dev.tfvars -var="subscription_id=YOUR_SUB_ID" -var="admin_token=YOUR_TOKEN"
```

## Outputs

- `backend_url` – public API endpoint
- `frontend_url` – public frontend URL
- `swa_api_key` – deploy token for SWA (sensitive)
- `acr_login_server` – ACR for pushing images
- `resource_group_name` – RG name

## Cost Notes

- Cosmos DB serverless: pay-per-request, negligible for a 1-day event
- Container App: scale-to-zero, billed only when processing requests
- Static Web App: Free tier
- Container Registry Basic: ~$0.17/day
- **Total estimated cost for 1 day: < $2**
