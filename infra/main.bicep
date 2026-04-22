// ============================================================================
// BankPulse AI — Phase 1 Infrastructure
// Provisions: ADLS Gen2 storage, Azure SQL (free offer), Key Vault.
// ============================================================================

targetScope = 'resourceGroup'

// ---------- Parameters ------------------------------------------------------

@description('Base name used as a prefix for all resources')
param baseName string = 'bankpulse'

@description('Environment tag')
@allowed([ 'dev', 'prod' ])
param environment string = 'dev'

@description('Azure region. Defaults to the resource group region.')
param location string = resourceGroup().location

@description('SQL Server admin login name')
param sqlAdminLogin string

@description('SQL Server admin password. Must meet Azure complexity requirements.')
@secure()
param sqlAdminPassword string

@description('Your current public IP address, for SQL firewall allow-list')
param clientIpAddress string

// ---------- Variables -------------------------------------------------------

// Resource names must be globally unique (for storage) or unique per subscription.
// Derive a short deterministic suffix from the resource group ID so names are
// unique but reproducible across re-deploys.
var suffix = take(uniqueString(resourceGroup().id), 6)
var storageAccountName = toLower('${baseName}${environment}${suffix}')
var keyVaultName       = '${baseName}-kv-${suffix}'
var sqlServerName      = '${baseName}-sql-${environment}-${suffix}'
var sqlDatabaseName    = '${baseName}db'

var tags = {
  project:     'bankpulse-ai'
  environment: environment
  managedBy:   'bicep'
}
// ---------- ADLS Gen2 storage ----------------------------------------------

// Standard storage account + hierarchical namespace = ADLS Gen2.
// The HNS switch is what gives us real folder semantics (rename, list, ACLs
// per folder) instead of flat blob "pseudo-paths". Spark expects this.
resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageAccountName
  location: location
  tags: tags
  sku: { name: 'Standard_LRS' }       // Locally-redundant = cheapest. Fine for dev.
  kind: 'StorageV2'
  properties: {
    isHnsEnabled: true                 // The ADLS Gen2 switch
    accessTier: 'Hot'
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    allowSharedKeyAccess: true         // Simpler for Phase 1; we'll tighten later
    supportsHttpsTrafficOnly: true
  }
}

// The blob service is a sub-resource of the account. We need a reference to
// it to create containers underneath.
resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storage
  name: 'default'                      // Must be exactly 'default' — Azure quirk
}

// Medallion architecture: raw → cleaned → analytics-ready
resource bronze 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: 'bronze'
}
resource silver 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: 'silver'
}
resource gold 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: 'gold'
}
// ---------- Key Vault -------------------------------------------------------

// RBAC-based access (not legacy access policies). Modern best practice —
// you grant access by assigning Azure roles, same as any other resource.
resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: keyVaultName
  location: location
  tags: tags
  properties: {
    sku: { family: 'A', name: 'standard' }
    tenantId: subscription().tenantId
    enableRbacAuthorization: true
    enabledForTemplateDeployment: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
    publicNetworkAccess: 'Enabled'
  }
}

// ---------- Azure SQL Database (free offer) --------------------------------

resource sqlServer 'Microsoft.Sql/servers@2023-08-01-preview' = {
  name: sqlServerName
  location: location
  tags: tags
  properties: {
    administratorLogin: sqlAdminLogin
    administratorLoginPassword: sqlAdminPassword
    version: '12.0'
    minimalTlsVersion: '1.2'
    publicNetworkAccess: 'Enabled'
  }
}

// Firewall rule: allow your laptop's public IP to connect
resource fwClient 'Microsoft.Sql/servers/firewallRules@2023-08-01-preview' = {
  parent: sqlServer
  name: 'AllowClientIP'
  properties: {
    startIpAddress: clientIpAddress
    endIpAddress: clientIpAddress
  }
}

// The magic 0.0.0.0 rule — lets other Azure services (e.g. Power BI Service)
// reach the server. Doesn't mean "all of Azure" — it means "Azure-managed
// services with trusted identities".
resource fwAzure 'Microsoft.Sql/servers/firewallRules@2023-08-01-preview' = {
  parent: sqlServer
  name: 'AllowAzureServices'
  properties: {
    startIpAddress: '0.0.0.0'
    endIpAddress: '0.0.0.0'
  }
}

// The free offer: General Purpose serverless with auto-pause.
// useFreeLimit = true enables the 100k vCore-seconds + 32 GB/month allowance.
// AutoPause as the overage behaviour is our hard ceiling — the DB simply
// stops working until next month rather than billing.
resource sqlDb 'Microsoft.Sql/servers/databases@2023-08-01-preview' = {
  parent: sqlServer
  name: sqlDatabaseName
  location: location
  tags: tags
  sku: {
    name: 'GP_S_Gen5'
    tier: 'GeneralPurpose'
    family: 'Gen5'
    capacity: 2
  }
  properties: {
    collation: 'SQL_Latin1_General_CP1_CI_AS'
    maxSizeBytes: 34359738368        // 32 GB
    autoPauseDelay: 60               // pause after 60 minutes idle
    minCapacity: json('0.5')
    useFreeLimit: true
    freeLimitExhaustionBehavior: 'AutoPause'
  }
}

// ---------- Outputs ---------------------------------------------------------

// Printed after deployment. We'll copy these into our .env.
output storageAccountName string = storage.name
output keyVaultName       string = keyVault.name
output sqlServerName      string = sqlServer.name
output sqlServerFqdn      string = sqlServer.properties.fullyQualifiedDomainName
output sqlDatabaseName    string = sqlDb.name
output bronzeContainerUrl string = '${storage.properties.primaryEndpoints.dfs}bronze'
