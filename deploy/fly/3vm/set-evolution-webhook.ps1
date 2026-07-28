param(
  [ValidateSet("production", "test")]
  [string]$Mode = "test",
  [string]$Instance = "loja1",
  [string]$EvolutionBaseUrl = "https://evolution2037.fly.dev",
  [string]$N8nBaseUrl = "https://n8n2037.fly.dev"
)

$ErrorActionPreference = "Stop"
$secretsFile = Join-Path $PSScriptRoot ".secrets.local"
$keyFile = Join-Path $PSScriptRoot ".evolution_key.local"
$evolutionKey = $env:EVOLUTION_API_KEY

if (-not $evolutionKey -and (Test-Path $keyFile)) {
  $evolutionKey = (Get-Content $keyFile -Raw).Trim()
}
if (-not $evolutionKey -and (Test-Path $secretsFile)) {
  $line = Get-Content $secretsFile |
    Where-Object { $_ -match '^\s*EVOLUTION_API_KEY\s*=' } |
    Select-Object -First 1
  if ($line) {
    $evolutionKey = $line.Substring($line.IndexOf("=") + 1).Trim()
  }
}
if (-not $evolutionKey) {
  throw "EVOLUTION_API_KEY ausente no ambiente, .evolution_key.local ou .secrets.local"
}

$webhookPath = if ($Mode -eq "test") { "whatsapp-ai-teste" } else { "whatsapp-ai" }
$webhookUrl = "$($N8nBaseUrl.TrimEnd('/'))/webhook/$webhookPath"
$endpoint = "$($EvolutionBaseUrl.TrimEnd('/'))/webhook/set/$Instance"
$headers = @{
  apikey = $evolutionKey
  "Content-Type" = "application/json"
}
$body = @{
  webhook = @{
    enabled = $true
    url = $webhookUrl
    events = @("MESSAGES_UPSERT")
  }
} | ConvertTo-Json -Depth 5

$null = Invoke-RestMethod -Method Post -Uri $endpoint -Headers $headers -Body $body
Write-Host "Evolution configurada: instance=$Instance mode=$Mode webhook=$webhookUrl"
