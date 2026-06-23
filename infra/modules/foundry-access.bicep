@description('Name of the existing Microsoft Foundry (AIServices) account to grant access to.')
param foundryAccountName string

@description('Principal ID of the managed identity to grant access.')
param managedIdentityPrincipalId string

resource foundryAccount 'Microsoft.CognitiveServices/accounts@2024-10-01' existing = {
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
