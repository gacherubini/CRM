# Prepares n8n workflow JSON with Fly hosts + tokens from .secrets.local
# Does NOT print secret values.
$ErrorActionPreference = "Stop"
$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
if (-not (Test-Path (Join-Path $root "n8n\workflow-ai-nao-salvos.json"))) {
  $root = (Get-Location).Path
}
$canonical = Join-Path $root "n8n\workflow-ai-nao-salvos.json"
$secretsFile = Join-Path $PSScriptRoot ".secrets.local"
$outFile = Join-Path $PSScriptRoot "workflow-fly.ready.json"

if (-not (Test-Path $canonical)) { throw "canonical workflow not found: $canonical" }
if (-not (Test-Path $secretsFile)) { throw "missing $secretsFile" }

$secrets = @{}
Get-Content $secretsFile | ForEach-Object {
  if ($_ -match '^\s*#' -or $_ -notmatch '=') { return }
  $i = $_.IndexOf('=')
  $k = $_.Substring(0, $i).Trim()
  $v = $_.Substring($i + 1).Trim()
  if ($k -and $v) { $secrets[$k] = $v }
}

# Prefer public HTTPS: n8n reaches these reliably.
# flycast needs private IPv6 + nginx listen [::] (see nginx-edge.conf).
$chatbotBase = if ($env:CHATBOT_BASE_URL) { $env:CHATBOT_BASE_URL } else { "https://app2037.fly.dev" }
$evolutionBase = if ($env:EVOLUTION_BASE_URL) { $env:EVOLUTION_BASE_URL } else { "https://evolution2037.fly.dev" }
$instance = if ($env:EVOLUTION_INSTANCE) { $env:EVOLUTION_INSTANCE } else { "loja1" }

$json = Get-Content $canonical -Raw -Encoding UTF8
$json = $json.Replace("http://chatbot-api:8000", $chatbotBase)
$json = $json.Replace("http://evolution:8080", $evolutionBase)
$json = $json.Replace("__INSTANCE__", $instance)
$json = $json.Replace("__CHATBOT_TOKEN__", $secrets["CHATBOT_API_TOKEN"])
$json = $json.Replace("__CHATBOT_WEBHOOK_TOKEN__", $secrets["CHATBOT_WEBHOOK_TOKEN"])

# Evolution apikey from env EVOLUTION_API_KEY if set (not in secrets.local by default)
if ($env:EVOLUTION_API_KEY) {
  # replace placeholder patterns if any remain; also set common apikey header values later in import
  $json = $json.Replace("__EVOLUTION_KEY__", $env:EVOLUTION_API_KEY)
}

# Activate for import
$json = $json.Replace('"active": false', '"active": true')

[System.IO.File]::WriteAllText($outFile, $json, [System.Text.UTF8Encoding]::new($false))
Write-Host "wrote $outFile (len=$($json.Length)) chatbot=$chatbotBase evolution=$evolutionBase instance=$instance"
Write-Host "tokens: chatbot_api=$($secrets['CHATBOT_API_TOKEN'].Length) webhook=$($secrets['CHATBOT_WEBHOOK_TOKEN'].Length)"
