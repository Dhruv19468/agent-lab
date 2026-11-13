<#
.SYNOPSIS
  One-time Azure setup for Agent Lab. Safe to run again: it skips what already exists.

.DESCRIPTION
  In one resource group (default rg-agent-lab) it creates:
    - Azure Container Registry           the Docker images (built in Azure: no local Docker needed)
    - Azure Database for PostgreSQL      Flexible Server, Burstable B1ms, database agent_lab_db
    - Storage account + Blob container   "agentdata" with your data/raw (and data/gold, if present)
    - Container Apps environment         + log workspace
    - Container App ca-<prefix>-api      FastAPI backend: internal only, managed identity
    - Container App ca-<prefix>-web      nginx + React: the public URL, protected by a password
    - (optional) GitHub OIDC login       so GitHub Actions can deploy without a stored password

  It reuses your existing Foundry resource (models + agent publishing). Endpoint, key, deployment and
  project endpoint are read from backend/.env, so the key is never typed or printed.

  The backend's managed identity gets:
    - "Storage Blob Data Contributor" on the storage account  (read the dataset, save outputs)
    - "Azure AI Developer" on the Foundry resource            (publish/delete agents, list models)
  No storage key is used anywhere.

.EXAMPLE
  cd C:\dev\agent-lab
  az login
  .\deploy\azure\setup.ps1 -GitHubRepo yourname/agent-lab
#>
param(
    [string]$Prefix = "agentlab",
    [string]$ResourceGroup = "rg-agent-lab",
    [string]$Location = "",            # empty: the resource group's location
    [string]$FoundryResource = "",     # empty: the AIServices resource found in the resource group
    [string]$GitHubRepo = "",          # "owner/repo"; empty = skip the GitHub OIDC step
    [string]$SiteUser = "lab"
)

$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $true
$root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $root

function Step($text) { Write-Host "`n==> $text" -ForegroundColor Cyan }
function Exists([scriptblock]$probe) {
    $PSNativeCommandUseErrorActionPreference = $false
    & $probe 2>$null | Out-Null
    $ok = ($LASTEXITCODE -eq 0)
    $PSNativeCommandUseErrorActionPreference = $true
    return $ok
}
function Retry([scriptblock]$action, [string]$what, [int]$tries = 10) {
    # New role assignments take a few minutes to apply: try again instead of failing.
    for ($i = 1; $i -le $tries; $i++) {
        $PSNativeCommandUseErrorActionPreference = $false
        & $action
        $code = $LASTEXITCODE
        $PSNativeCommandUseErrorActionPreference = $true
        if ($code -eq 0) { return }
        Write-Host "   $what not ready yet (attempt $i/$tries); waiting 30 s for permissions to apply…"
        Start-Sleep -Seconds 30
    }
    throw "$what kept failing. Check the role assignment, then run the script again."
}
function New-Password([int]$length = 24) {
    # Letters and digits only: safe inside a database URL. At least one of each kind.
    $chars = "abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789".ToCharArray()
    do { $p = -join (1..$length | ForEach-Object { $chars | Get-Random }) }
    until ($p -cmatch "[a-z]" -and $p -cmatch "[A-Z]" -and $p -match "\d")
    return $p
}

# --- inputs ----------------------------------------------------------------------------------
Step "Reading Azure settings from backend/.env"
$envFile = Join-Path $root "backend\.env"
if (-not (Test-Path $envFile)) { throw "backend/.env not found." }
$dotenv = @{}
Get-Content $envFile | Where-Object { $_ -match "^\s*([A-Z_]+)\s*=\s*(.*)$" } | ForEach-Object {
    $dotenv[$Matches[1]] = $Matches[2].Trim().Trim('"').Trim("'")
}
foreach ($name in "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_KEY", "AZURE_OPENAI_DEPLOYMENT") {
    if (-not $dotenv[$name]) { throw "$name is missing in backend/.env" }
}
$foundryEndpoint = "$($dotenv.FOUNDRY_PROJECT_ENDPOINT)"
$extraDeployments = "$($dotenv.AZURE_OPENAI_DEPLOYMENTS)"
Write-Host "Models: $($dotenv.AZURE_OPENAI_ENDPOINT) (default $($dotenv.AZURE_OPENAI_DEPLOYMENT))"
if ($foundryEndpoint) { Write-Host "Foundry project: $foundryEndpoint" } else { Write-Host "Foundry project: not set (publish stays inside Agent Lab)" }

foreach ($file in "backend\uv.lock", "frontend\package-lock.json", "data\raw") {
    if (-not (Test-Path (Join-Path $root $file))) { throw "$file is missing. (package-lock.json: run 'npm install' in frontend once.)" }
}

# Passwords are made once and kept in deploy/azure/secrets.local.json (git-ignored).
$secretsFile = Join-Path $PSScriptRoot "secrets.local.json"
if (Test-Path $secretsFile) { $secrets = Get-Content $secretsFile | ConvertFrom-Json }
else {
    $secrets = [pscustomobject]@{ postgresPassword = New-Password; sitePassword = New-Password 16 }
    $secrets | ConvertTo-Json | Set-Content $secretsFile
}

$account = az account show --query "{id:id, name:name, user:user.name}" -o json | ConvertFrom-Json
$subscription = $account.id
Write-Host "Signed in as $($account.user), subscription '$($account.name)'"

if (-not (Exists { az group show -n $ResourceGroup })) {
    if (-not $Location) { $Location = "eastus" }
    az group create -n $ResourceGroup -l $Location -o none
}
if (-not $Location) { $Location = az group show -n $ResourceGroup --query location -o tsv }

$suffix = $subscription.Substring(0, 6).ToLower()          # same every run, unique enough
$acr = ("acr$Prefix$suffix" -replace "[^a-z0-9]", "")
$pg = "pg-$Prefix-$suffix"
$storage = ("st$Prefix$suffix" -replace "[^a-z0-9]", "")
if ($storage.Length -gt 24) { $storage = $storage.Substring(0, 24) }
$container = "agentdata"
$envName = "cae-$Prefix"
$api = "ca-$Prefix-api"
$web = "ca-$Prefix-web"
$dbName = "agent_lab_db"
$dbUser = "labadmin"
Write-Host "Resource group $ResourceGroup ($Location): $acr, $pg, $storage, $envName, $api, $web"

foreach ($p in "Microsoft.App", "Microsoft.OperationalInsights", "Microsoft.ContainerRegistry", "Microsoft.DBforPostgreSQL", "Microsoft.Storage") {
    az provider register --namespace $p --wait | Out-Null
}
az extension add --name containerapp --upgrade --only-show-errors | Out-Null

# --- Foundry resource -------------------------------------------------------------------------
$foundryId = ""
if ($foundryEndpoint -or $FoundryResource) {
    Step "Finding the Foundry resource"
    if (-not $FoundryResource) {
        $FoundryResource = az cognitiveservices account list -g $ResourceGroup --query "[?kind=='AIServices'] | [0].name" -o tsv
    }
    if (-not $FoundryResource) { throw "No AIServices (Foundry) resource in $ResourceGroup. Pass -FoundryResource <name>." }
    $foundryId = az cognitiveservices account show -n $FoundryResource -g $ResourceGroup --query id -o tsv
    Write-Host "Foundry resource: $FoundryResource"
}

# --- container registry -----------------------------------------------------------------------
Step "Container registry $acr"
if (-not (Exists { az acr show -n $acr -g $ResourceGroup })) {
    az acr create -n $acr -g $ResourceGroup -l $Location --sku Basic --admin-enabled true -o none
}
$acrServer = az acr show -n $acr --query loginServer -o tsv
$acrPassword = az acr credential show -n $acr --query "passwords[0].value" -o tsv

# --- PostgreSQL --------------------------------------------------------------------------------
Step "PostgreSQL $pg (5-10 minutes the first time)"
if (-not (Exists { az postgres flexible-server show -n $pg -g $ResourceGroup })) {
    az postgres flexible-server create -n $pg -g $ResourceGroup -l $Location `
        --tier Burstable --sku-name Standard_B1ms --storage-size 32 --version 16 `
        --admin-user $dbUser --admin-password $secrets.postgresPassword `
        --public-access 0.0.0.0 --yes -o none   # 0.0.0.0 = allow Azure services (the Container App)
}
if (-not (Exists { az postgres flexible-server db show -s $pg -g $ResourceGroup -d $dbName })) {
    az postgres flexible-server db create -s $pg -g $ResourceGroup -d $dbName -o none
}
$pgHost = az postgres flexible-server show -n $pg -g $ResourceGroup --query fullyQualifiedDomainName -o tsv
$databaseUrl = "postgresql+asyncpg://${dbUser}:$($secrets.postgresPassword)@${pgHost}:5432/${dbName}?ssl=require"

# --- Blob Storage + data -----------------------------------------------------------------------
Step "Storage account $storage, Blob container $container"
if (-not (Exists { az storage account show -n $storage -g $ResourceGroup })) {
    az storage account create -n $storage -g $ResourceGroup -l $Location --sku Standard_LRS --kind StorageV2 `
        --min-tls-version TLS1_2 --allow-blob-public-access false -o none
}
$storageId = az storage account show -n $storage -g $ResourceGroup --query id -o tsv
$storageUrl = az storage account show -n $storage -g $ResourceGroup --query primaryEndpoints.blob -o tsv
$storageUrl = $storageUrl.TrimEnd("/")

# You upload with your own sign-in (no key), so you need the data role too.
$me = az ad signed-in-user show --query id -o tsv
Exists { az role assignment create --assignee $me --role "Storage Blob Data Contributor" --scope $storageId -o none } | Out-Null
Retry { az storage container create --name $container --account-name $storage --auth-mode login -o none } "Creating the Blob container"

Step "Uploading data/raw (and data/gold, if present) to the container"
foreach ($folder in "raw", "gold") {
    $source = Join-Path $root "data\$folder"
    if (Test-Path $source) {
        Retry { az storage blob upload-batch --account-name $storage --auth-mode login -d $container `
            -s $source --destination-path $folder --overwrite --no-progress -o none } "Uploading data/$folder"
        Write-Host "Uploaded data/$folder"
    }
}

# --- Container Apps environment ----------------------------------------------------------------
Step "Container Apps environment $envName"
if (-not (Exists { az containerapp env show -n $envName -g $ResourceGroup })) {
    az containerapp env create -n $envName -g $ResourceGroup -l $Location -o none
}
$envId = az containerapp env show -n $envName -g $ResourceGroup --query id -o tsv

# --- images ----------------------------------------------------------------------------------
Step "Building images in ACR (no local Docker needed)"
az acr build -r $acr -t agent-lab-api:initial ./backend --no-logs -o none
az acr build -r $acr -t agent-lab-web:initial ./frontend --no-logs -o none

# --- backend app (YAML: managed identity, secrets and many settings) ---------------------------
Step "Backend Container App $api"
$apiExists = Exists { az containerapp show -n $api -g $ResourceGroup }
$apiImage = if ($apiExists) {
    az containerapp show -n $api -g $ResourceGroup --query "properties.template.containers[0].image" -o tsv
} else { "$acrServer/agent-lab-api:initial" }
$yaml = @"
location: $Location
name: $api
type: Microsoft.App/containerApps
identity:
  type: SystemAssigned
properties:
  managedEnvironmentId: $envId
  configuration:
    activeRevisionsMode: Single
    ingress:
      external: false
      allowInsecure: true
      targetPort: 8080
      transport: http
    registries:
      - server: $acrServer
        username: $acr
        passwordSecretRef: acr-password
    secrets:
      - name: acr-password
        value: "$acrPassword"
      - name: database-url
        value: "$databaseUrl"
      - name: azure-openai-key
        value: "$($dotenv.AZURE_OPENAI_API_KEY)"
  template:
    containers:
      - name: api
        image: $apiImage
        resources:
          cpu: 0.5
          memory: 1Gi
        env:
          - name: ENVIRONMENT
            value: azure
          - name: DATABASE_URL
            secretRef: database-url
          - name: DATABASE_SCHEMA
            value: al
          - name: RUN_ALEMBIC_ON_STARTUP
            value: "true"
          - name: AZURE_OPENAI_ENDPOINT
            value: "$($dotenv.AZURE_OPENAI_ENDPOINT)"
          - name: AZURE_OPENAI_DEPLOYMENT
            value: "$($dotenv.AZURE_OPENAI_DEPLOYMENT)"
          - name: AZURE_OPENAI_DEPLOYMENTS
            value: "$extraDeployments"
          - name: AZURE_OPENAI_API_KEY
            secretRef: azure-openai-key
          - name: AZURE_OPENAI_TIMEOUT_SECONDS
            value: "600"
          - name: FOUNDRY_PROJECT_ENDPOINT
            value: "$foundryEndpoint"
          - name: FOUNDRY_AUTH_MODE
            value: entra
          - name: AGENT_STORAGE
            value: blob
          - name: AZURE_STORAGE_ACCOUNT_URL
            value: "$storageUrl"
          - name: AZURE_STORAGE_CONTAINER
            value: "$container"
        probes:
          - type: Liveness
            httpGet:
              path: /api/health
              port: 8080
            initialDelaySeconds: 20
            periodSeconds: 30
    scale:
      minReplicas: 0
      maxReplicas: 1
"@
$yamlFile = Join-Path ([IO.Path]::GetTempPath()) "agent-lab-api.yaml"
Set-Content -Path $yamlFile -Value $yaml -Encoding utf8
try {
    if ($apiExists) { az containerapp update -n $api -g $ResourceGroup --yaml $yamlFile -o none }
    else { az containerapp create -n $api -g $ResourceGroup --yaml $yamlFile -o none }
} finally { Remove-Item $yamlFile -Force }   # it contained secrets

Step "Permissions for the backend's managed identity"
$principal = az containerapp show -n $api -g $ResourceGroup --query identity.principalId -o tsv
Exists { az role assignment create --assignee-object-id $principal --assignee-principal-type ServicePrincipal `
    --role "Storage Blob Data Contributor" --scope $storageId -o none } | Out-Null
Write-Host "Storage Blob Data Contributor on $storage"
if ($foundryId) {
    Exists { az role assignment create --assignee-object-id $principal --assignee-principal-type ServicePrincipal `
        --role "Azure AI Developer" --scope $foundryId -o none } | Out-Null
    Write-Host "Azure AI Developer on $FoundryResource"
}
Write-Host "Roles take a few minutes to apply; the backend picks them up on its next request."

# --- frontend app ------------------------------------------------------------------------------
Step "Frontend Container App $web"
if (-not (Exists { az containerapp show -n $web -g $ResourceGroup })) {
    az containerapp create -n $web -g $ResourceGroup --environment $envName `
        --image "$acrServer/agent-lab-web:initial" `
        --registry-server $acrServer --registry-username $acr --registry-password $acrPassword `
        --ingress external --target-port 80 --cpu 0.25 --memory 0.5Gi --min-replicas 0 --max-replicas 1 `
        --secrets "site-password=$($secrets.sitePassword)" `
        --env-vars "BACKEND_URL=http://$api" "BASIC_AUTH_USER=$SiteUser" "BASIC_AUTH_PASSWORD=secretref:site-password" -o none
}
$webUrl = "https://" + (az containerapp show -n $web -g $ResourceGroup --query properties.configuration.ingress.fqdn -o tsv)

# --- GitHub Actions login (OIDC: no password stored in GitHub) ---------------------------------
if ($GitHubRepo) {
    Step "GitHub OIDC for $GitHubRepo"
    $appName = "gh-$Prefix-deploy"
    $appId = az ad app list --display-name $appName --query "[0].appId" -o tsv
    if (-not $appId) { $appId = az ad app create --display-name $appName --query appId -o tsv }
    if (-not (Exists { az ad sp show --id $appId })) { az ad sp create --id $appId -o none }
    $credentialFile = Join-Path ([IO.Path]::GetTempPath()) "gh-credential.json"
    @{ name = "main-branch"; issuer = "https://token.actions.githubusercontent.com"
       subject = "repo:${GitHubRepo}:ref:refs/heads/main"; audiences = @("api://AzureADTokenExchange") } |
        ConvertTo-Json | Set-Content $credentialFile
    $existing = az ad app federated-credential list --id $appId --query "[?name=='main-branch'] | length(@)" -o tsv
    if ($existing -eq "0") { az ad app federated-credential create --id $appId --parameters $credentialFile -o none }
    Remove-Item $credentialFile
    $rgId = az group show -n $ResourceGroup --query id -o tsv
    # Contributor on this resource group only: enough to build images and update the apps.
    Exists { az role assignment create --assignee $appId --role Contributor --scope $rgId -o none } | Out-Null
    $tenant = az account show --query tenantId -o tsv

    Write-Host "`nAdd these to GitHub (repo Settings > Secrets and variables > Actions), or run:" -ForegroundColor Yellow
    Write-Host "  gh secret set AZURE_CLIENT_ID --body $appId --repo $GitHubRepo"
    Write-Host "  gh secret set AZURE_TENANT_ID --body $tenant --repo $GitHubRepo"
    Write-Host "  gh secret set AZURE_SUBSCRIPTION_ID --body $subscription --repo $GitHubRepo"
    Write-Host "  gh variable set AZURE_RESOURCE_GROUP --body $ResourceGroup --repo $GitHubRepo"
    Write-Host "  gh variable set ACR_NAME --body $acr --repo $GitHubRepo"
    Write-Host "  gh variable set API_APP --body $api --repo $GitHubRepo"
    Write-Host "  gh variable set WEB_APP --body $web --repo $GitHubRepo"
}

Step "Done"
Write-Host "Open:      $webUrl"
Write-Host "User:      $SiteUser"
Write-Host "Password:  in deploy/azure/secrets.local.json (sitePassword)"
Write-Host "Data:      $storageUrl/$container  (raw/, agent-output/, _cache/)"
Write-Host "The first request wakes the apps (scale-to-zero); give it ~30 seconds."
