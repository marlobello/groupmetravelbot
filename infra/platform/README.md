# Platform / Center-of-Excellence templates

These templates are **owned by the platform / Center-of-Excellence (CoE) team**,
not by the application team or its CI/CD pipeline. They are deployed **out of
band** against resource groups the app pipeline has no write access to.

## Separation of duties

| Concern | Owner | Where | Deployed by |
| --- | --- | --- | --- |
| Foundry account + project (`sensei`), models, guardrails, content filters, quotas | Platform / CoE | `rg-foundry` | CoE, out of band |
| Granting an app identity **consumer** access to the project | Platform / CoE | `rg-foundry` | CoE, via `foundry-project-access.bicep` |
| App identity, storage, Container App, the app image | App team | `rg-travelbot` | App CI/CD (`infra/main.bicep`, `.github/workflows/`) |

The application CI/CD service principal has **no role assignments and no write
access in `rg-foundry`**. `infra/main.bicep` never references the Foundry
account — it only consumes the project endpoints handed to it as parameters
(`foundryProjectEndpoint`, `foundryOpenAiEndpoint`).

## `foundry-project-access.bicep`

Grants an application's managed identity the minimum roles needed to *consume*
the shared Foundry project:

- **Foundry User** — call the Agent Service / project (incl. the hosted Web Search tool)
- **Cognitive Services OpenAI User** — call Azure OpenAI inference (attachment OCR)

### Handoff flow

1. App team deploys `infra/main.bicep`; it outputs `managedIdentityPrincipalId`.
2. App team gives that principal ID (plus the desired Foundry account name) to the CoE.
3. CoE deploys this template against the Foundry resource group:

```bash
az deployment group create \
  -g rg-foundry \
  -f infra/platform/foundry-project-access.bicep \
  -p foundryAccountName=sensei-resource \
     managedIdentityPrincipalId=<app-mi-principal-id>
```

The CoE in turn hands the app team the project endpoints to set as parameters
in the app deployment.
