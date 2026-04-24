@description('Azure region for the OpenAI account.')
param location string

@description('Name of the Azure OpenAI account.')
param openaiAccountName string

@description('Principal ID of the managed identity for RBAC.')
param managedIdentityPrincipalId string

resource openaiAccount 'Microsoft.CognitiveServices/accounts@2024-04-01-preview' = {
  name: openaiAccountName
  location: location
  kind: 'OpenAI'
  sku: {
    name: 'S0'
  }
  properties: {
    customSubDomainName: openaiAccountName
    publicNetworkAccess: 'Enabled'
  }
}

resource gpt4oDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-04-01-preview' = {
  parent: openaiAccount
  name: 'gpt-4o'
  sku: {
    name: 'Standard'
    capacity: 1
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'gpt-4o'
      version: '2024-11-20'
    }
  }
}

// Cognitive Services OpenAI User
var openaiUserRoleId = '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'

resource openaiRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(openaiAccount.id, managedIdentityPrincipalId, openaiUserRoleId)
  scope: openaiAccount
  properties: {
    principalId: managedIdentityPrincipalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', openaiUserRoleId)
    principalType: 'ServicePrincipal'
  }
}

@description('Azure OpenAI account endpoint.')
output openaiEndpoint string = openaiAccount.properties.endpoint
