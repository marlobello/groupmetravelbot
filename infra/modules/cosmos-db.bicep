@description('Azure region for Cosmos DB resources.')
param location string

@description('Name of the Cosmos DB account.')
param cosmosAccountName string

@description('Principal ID of the managed identity for data-plane RBAC.')
param managedIdentityPrincipalId string

resource cosmosAccount 'Microsoft.DocumentDB/databaseAccounts@2024-05-15' = {
  name: cosmosAccountName
  location: location
  kind: 'GlobalDocumentDB'
  properties: {
    databaseAccountOfferType: 'Standard'
    capabilities: [
      {
        name: 'EnableServerless'
      }
    ]
    locations: [
      {
        locationName: location
        failoverPriority: 0
      }
    ]
    consistencyPolicy: {
      defaultConsistencyLevel: 'Session'
    }
  }
}

resource database 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2024-05-15' = {
  parent: cosmosAccount
  name: 'travelbot'
  properties: {
    resource: {
      id: 'travelbot'
    }
  }
}

resource tripsContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = {
  parent: database
  name: 'trips'
  properties: {
    resource: {
      id: 'trips'
      partitionKey: {
        paths: [
          '/groupId'
        ]
        kind: 'Hash'
      }
      indexingPolicy: {
        indexingMode: 'consistent'
        automatic: true
        includedPaths: [
          { path: '/*' }
        ]
        excludedPaths: [
          { path: '/details/*' }
          { path: '/"_etag"/?' }
        ]
      }
    }
  }
}

// Cosmos DB Built-in Data Contributor role
var dataContributorRoleId = '00000000-0000-0000-0000-000000000002'

resource sqlRoleAssignment 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2024-05-15' = {
  parent: cosmosAccount
  name: guid(cosmosAccount.id, managedIdentityPrincipalId, dataContributorRoleId)
  properties: {
    principalId: managedIdentityPrincipalId
    roleDefinitionId: '${cosmosAccount.id}/sqlRoleDefinitions/${dataContributorRoleId}'
    scope: cosmosAccount.id
  }
}

@description('Cosmos DB account endpoint.')
output cosmosEndpoint string = cosmosAccount.properties.documentEndpoint
