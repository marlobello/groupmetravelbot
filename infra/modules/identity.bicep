@description('Azure region for the managed identity.')
param location string

@description('Name of the user-assigned managed identity.')
param managedIdentityName string

resource managedIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: managedIdentityName
  location: location
}

@description('Resource ID of the managed identity.')
output managedIdentityId string = managedIdentity.id

@description('Principal ID of the managed identity.')
output managedIdentityPrincipalId string = managedIdentity.properties.principalId

@description('Client ID of the managed identity.')
output managedIdentityClientId string = managedIdentity.properties.clientId
