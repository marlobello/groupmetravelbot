// ─────────────────────────────────────────────────────────────────────
// PLATFORM / CENTER-OF-EXCELLENCE TEMPLATE — deployed OUT OF BAND.
//
// This template is OWNED BY THE PLATFORM/CoE TEAM, not the application
// pipeline. It grants an application's managed identity consumer access to
// the shared Foundry account/project. It is intentionally NOT referenced by
// infra/main.bicep, so the app's CI/CD never needs write access to the
// Foundry resource group.
//
// Deploy (by the CoE, against the Foundry resource group):
//   az deployment group create \
//     -g rg-foundry \
//     -f infra/platform/foundry-project-access.bicep \
//     -p foundryAccountName=sensei-resource \
//        managedIdentityPrincipalId=<app-mi-principal-id>
//
// The <app-mi-principal-id> is published as the `managedIdentityPrincipalId`
// output of the application deployment (infra/main.bicep).
// ─────────────────────────────────────────────────────────────────────

@description('Name of the existing Microsoft Foundry (AIServices) account to grant access to.')
param foundryAccountName string

@description('Principal ID of the application managed identity to grant access.')
param managedIdentityPrincipalId string

resource foundryAccount 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = {
  name: foundryAccountName
}

// Foundry User — call the Foundry Agent Service / project (e.g. the hosted Web Search tool)
var foundryUserRoleId = '53ca6127-db72-4b80-b1b0-d745d6d5456d'
// Cognitive Services OpenAI User — call Azure OpenAI inference (attachment OCR)
var openAiUserRoleId = '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'

resource foundryUserAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(foundryAccount.id, managedIdentityPrincipalId, foundryUserRoleId)
  scope: foundryAccount
  properties: {
    principalId: managedIdentityPrincipalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', foundryUserRoleId)
    principalType: 'ServicePrincipal'
  }
}

resource openAiUserAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(foundryAccount.id, managedIdentityPrincipalId, openAiUserRoleId)
  scope: foundryAccount
  properties: {
    principalId: managedIdentityPrincipalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', openAiUserRoleId)
    principalType: 'ServicePrincipal'
  }
}
