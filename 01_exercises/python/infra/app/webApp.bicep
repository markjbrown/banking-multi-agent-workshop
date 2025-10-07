param name string
param appServicePlanName string
param location string = resourceGroup().location


resource appServicePlan 'Microsoft.Web/serverfarms@2022-03-01' = {
  name: appServicePlanName
  location: location
  kind: 'linux'
  sku: {
    name: 'B1'   // Use P1V3 for large workloads
    tier: 'Basic' // Use PremiumV2 for large workloads
  }
  properties: {
    reserved: true
  }
}

resource webApp 'Microsoft.Web/sites@2022-03-01' = {
  name: name
  location: location
  kind: 'linux'
  properties: {
    serverFarmId: appServicePlan.id
    reserved: true
  }
}

output name string = webApp.name
output url string = 'https://${webApp.properties.defaultHostName}'
